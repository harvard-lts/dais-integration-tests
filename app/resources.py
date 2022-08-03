import re
import shutil
import time
import boto3
import requests
from flask_restx import Resource, Api
from flask import render_template
import os, os.path, json


def define_resources(app):
    api = Api(app, version='1.0', title='HDC Integration Tests',
              description='This project contains the integration tests for the HDC project')
    dashboard = api.namespace('/', description="This project contains the integration tests for the HDC project")

    # Env vars
    dataverse_endpoint = os.environ.get('DATAVERSE_ENDPOINT')
    admin_user_token = os.environ.get('ADMIN_USER_API_TOKEN')
    dataverse_s3_access_id = os.environ.get('AWS_ACCESS_KEY_ID')
    dataverse_s3_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    s3_bucket_name = os.environ.get('S3_BUCKET_NAME')
    dropbox_destination = os.environ.get('DROPBOX_DESTINATION')


    # Heartbeat/health check route
    @dashboard.route('/version', endpoint="version", methods=['GET'])
    class Version(Resource):
        def get(self):
            version = os.environ.get('APP_VERSION', "NOT FOUND")
            return {"version": version}

    @app.route('/hello-world')
    def hello_world():
        return render_template('index.html')

    @app.route('/apps/healthcheck')
    def app_healthchecks():
        num_failed_tests = 0
        tests_failed = []
        result = {"num_failed": num_failed_tests, "tests_failed": tests_failed}

        # Health Check Tests for DIMS
        health = requests.get(os.environ.get('DIMS_ENDPOINT') + '/health', verify=False)
        if health.status_code != 200:
            result["num_failed"] += 1
            result["tests_failed"].append("DIMS healthcheck")
            result["DIMS"] = {"status_code": health.status_code, "text": health.text}

        # Health Check Tests for DTS
        # TODO: status_code for DTS is 404, although the health check is successful
        health = requests.get(os.environ.get('DTS_ENDPOINT') + '/healthcheck', verify=False)
        json_health = json.loads(health.text)
        if json_health["status"] != "success":
            result["num_failed"] += 1
            result["tests_failed"].append("DTS healthcheck")
            result["DTS"] = {"status_code": health.status_code, "text": health.text}

        return json.dumps(result)

    @app.route('/ingest/happypath')
    def ingest_happypath():
        # 1) Call curator app for ingest
        # 2) Wait
        # 3) Check for loadreport file
        # 4) DIMS calls integration tests for status - check status
        pass


    @app.route('/DVIngest/createDataset')
    def dv_ingest_create_dataset():
        num_failed_tests = 0
        tests_failed = []
        result = {"num_failed": num_failed_tests, "tests_failed": tests_failed, "info": {}}

        app.logger.debug("Loading dataset dictionary")
        with open('/home/appuser/test_data/dataset-finch1.json') as dataset:
            data = dataset.read()

        # reconstructing the data as a dictionary
        random_dataset = json.loads(data)

        headers = {"X-Dataverse-key": admin_user_token}

        app.logger.debug("Creating dataset")
        # Create Dataset
        create_dataset = requests.post(
            dataverse_endpoint + '/api/dataverses/archived/datasets',
            json=random_dataset,
            headers=headers,
            verify=False)
        json_create_dataset = create_dataset.json()
        if json_create_dataset["status"] != "OK":
            result["num_failed"] += 1
            result["tests_failed"].append("Create Dataset")
            result["Failed Create Dataset"] = {"status_code": create_dataset.status_code,
                                               "text": json_create_dataset["message"]}
            return json.dumps(result)
        dataset_id = json_create_dataset["data"]["id"]
        persistent_id = json_create_dataset["data"]["persistentId"]
        result["info"]["persistentId"] = persistent_id
        result["info"]["datasetId"] = dataset_id
        result["info"]["Create Dataset"] = {"status_code": create_dataset.status_code}

        return json.dumps(result)


    @app.route('/DVIngest/publishDataset/<dataset_id>/<persistent_id>')
    def dv_ingest_publish_dataset(dataset_id=None, persistent_id=None):
        num_failed_tests = 0
        tests_failed = []
        result = {"num_failed": num_failed_tests, "tests_failed": tests_failed, "info": {}}

        headers = {"X-Dataverse-key": admin_user_token}

        if dataset_id == None or persistent_id == None:
            result["num_failed"] += 1
            result["tests_failed"].append("Publish Dataset")
            result["Failed Publish Dataset"] = {"invalid parameters": "dataset_id, persistent_id",
                                               "text": "Both parameters must be provided"}
            return json.dumps(result)

        app.logger.debug("Publishing dataset")
        # Publish Dataset
        publish_dataset = requests.post(
            dataverse_endpoint
            + '/api/datasets/:persistentId/actions/:publish?persistentId='
            + persistent_id
            + '&type=major'
            + '&assureIsIndexed=true',
            headers=headers,
            verify=False)
        json_publish_dataset = publish_dataset.json()

        # Wait for changes to take effect
        while publish_dataset.status_code != 200 and json_publish_dataset["message"] == "Dataset is awaiting indexing":
            app.logger.debug("Waiting in while loop dataset")
            time.sleep(3.0)
            publish_dataset = requests.post(
                dataverse_endpoint
                + '/api/datasets/:persistentId/actions/:publish?persistentId='
                + persistent_id
                + '&type=major'
                + '&assureIsIndexed=true',
                headers=headers,
                verify=False)
            json_publish_dataset = publish_dataset.json()

        if json_publish_dataset["status"] != "OK":
            result["num_failed"] += 1
            result["tests_failed"].append("Publish Dataset")
            result["Failed Publish Dataset"] = {"status_code": publish_dataset.status_code,
                                                "text": json_publish_dataset["message"]}
            return json.dumps(result)

        result["info"]["Publish Dataset"] = {"status_code": publish_dataset.status_code}
        return json.dumps(result)


    @app.route('/ingest/checkDropbox/<batchName>')
    def ingest_check_dropbox(batchName):
        num_failed_tests = 0
        tests_failed = []
        result = {"num_failed": num_failed_tests, "tests_failed": tests_failed, "info": {}}

        dataset_transferred = False
        app.logger.debug("checking dir: " + dropbox_destination + "/" + batchName)
        if os.path.exists(os.path.join(dropbox_destination, batchName)):
            dataset_transferred = True
            result["info"]["Dropbox Transfer Status"] = {
                "Found Dataset at Path": str(os.path.join(dropbox_destination, batchName))}

        if not dataset_transferred:
            result["num_failed"] += 1
            result["tests_failed"].append("Check Dropbox Transfer")
            result["Failed Dropbox Transfer"] = {
                "Dropbox Transfer Status": "Could not find " + batchName + " in dropbox " + dropbox_destination}

        return json.dumps(result)


    @app.route('/ingest/deleteFromDropbox/<batchName>')
    def ingest_delete_from_dropbox(batchName):
        num_failed_tests = 0
        tests_failed = []
        result = {"num_failed": num_failed_tests, "tests_failed": tests_failed, "info": {}}

        app.logger.debug("Delete test dataset from dropbox")
        if shutil.rmtree(os.path.join(dropbox_destination, batchName)):
            result["info"]["Delete Dataset From Dropbox"] = {
                "Deleted Dataset at Path": str(os.path.join(dropbox_destination, batchName))}
        else:
            result["num_failed"] += 1
            result["tests_failed"].append("Delete Dataset From Dropbox")
            result["Failed Delete From Dropbox"] = {"Delete From Dropbox": "Could not delete " +
                                                                           batchName + "in dropbox " + dropbox_destination}
        return json.dumps(result)
