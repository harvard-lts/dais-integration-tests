import glob
import shutil
import time
import requests
from flask_restx import Resource, Api
from flask import render_template
from flask import send_from_directory
import os, os.path, json
from datetime import datetime
import jwt
import jcs
from datetime import timedelta
import hashlib
import traceback


def define_resources(app):
    api = Api(app, version='1.0', title='HDC Integration Tests',
              description='This project contains the integration tests for the HDC project')
    dashboard = api.namespace('/', description="This project contains the integration tests for the HDC project")

    # Env vars
    dataverse_endpoint = os.environ.get('DATAVERSE_ENDPOINT')
    curator_app_endpoint = os.environ.get('CURATOR_APP_ENDPOINT')
    admin_user_token = os.environ.get('ADMIN_USER_API_TOKEN')
    base_dropbox_path = os.environ.get('BASE_DROPBOX_PATH')
    epadd_dropbox = os.environ.get('EPADD_DROPBOX')
    dataverse_dropbox = os.environ.get('DATAVERSE_DROPBOX')
    
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
    
    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(os.path.join(app.root_path, 'static'),
                            'favicon.ico',mimetype='image/vnd.microsoft.icon')
    
    @app.route('/etd/testbatch')
    def etd_batch_dais_tests():
        result = {"num_failed": 0, "tests_failed": [], "info": {}}
        # Create a unique OSN based on the timestamp
        osn_unique_appender = str(int(datetime.now().timestamp()))
        thesis_unique_name = "ETD_THESIS_" + osn_unique_appender
        test_data_dir = "test_data/submission_999999.zip"
        dest_data_dir = os.path.join(os.getenv("OUTGOING_TEST_DATA_DIR"), thesis_unique_name)

        shutil.copy2(test_data_dir, dest_data_dir)

        # Call DIMS ingest
        payload_data = _build_drs_admin_md_for_documentation(dest_data_dir, osn_unique_appender)

        try:
            json_ingest_response = _call_dims_api(payload_data)
        except Exception:
            exception_msg = traceback.format_exc()
            result["num_failed"] = 1
            result["tests_failed"].append("DIMS Ingest call failed " + exception_msg)
            return json.dumps(result)

        #json_ingest_response = ingest_etd_export.json()
        app.logger.debug("Ingest response")
        app.logger.debug(json_ingest_response)
        if json_ingest_response["status"] == "failure":
            result["num_failed"] = 1
            result["tests_failed"].append("DIMS Ingest call failed " + json_ingest_response)
            return json.dumps(result)
        
        result["info"]["ETD DAIS Call: "+test_data_dir] = {"status": json_ingest_response["status"]}

        return json.dumps(result)

    @app.route('/curatorApp/publishExport')
    def curator_app_publish_export():
        num_failed_tests = 0
        tests_failed = []
        result = {"num_failed": num_failed_tests, "tests_failed": tests_failed, "info": {}}

        publish_test_export = requests.get(
            curator_app_endpoint
            + '/testExport',
            verify=False)
        json_publish_export = publish_test_export.json()

        if json_publish_export["status"] != "success":
            result["num_failed"] += 1
            result["tests_failed"].append("ePADD Curator App Publish Export")
            result["Failed Publish ePADD Export"] = {"status_code": publish_test_export.status_code}
            return json.dumps(result)

        result["info"]["Publish ePADD Export"] = {"status_code": publish_test_export.status_code}

        return json.dumps(result)

    # Wait 5-10 mins before calling this after an ePADD export
    # is published to give the pipeline time to execute
    @app.route('/curatorApp/checkMockLoadreport/<test_batch_name>')
    def curator_app_mock_loadreport(test_batch_name=None):
        num_failed_tests = 0
        tests_failed = []
        result = {"num_failed": num_failed_tests, "tests_failed": tests_failed, "info": {}}

        if test_batch_name == None:
            result["num_failed"] += 1
            result["tests_failed"].append("Find Mock ePADD Loadreport")
            result["Failed Find Mock ePADD Loadreport"] = {"invalid parameters": "test_batch_name", "text": "test_batch_name cannot be None"}
            return json.dumps(result)

        app.logger.debug("Look for mock epadd loadreport in dropbox")
        if len(glob.glob(os.path.join(base_dropbox_path, "lts_load_reports", epadd_dropbox, "incoming", test_batch_name))) != 0:
            result["info"]["Find Mock ePADD Loadreport"] = {
                "Found Loadreport at Path": str(
                    os.path.join(base_dropbox_path, "lts_load_reports", epadd_dropbox, "incoming", test_batch_name))}
        else:
            result["num_failed"] += 1
            result["tests_failed"].append("Did Not Find Mock ePADD Loadreport")
            result["Failed Find Mock ePADD Loadreport"] = {"Find Mock ePADD Loadreport": "Could not find " +
                                                                                         test_batch_name + "in dropbox " + os.path.join(
                base_dropbox_path, "lts_load_reports", epadd_dropbox)}
        return json.dumps(result)
    
        
    @app.route('/curatorApp/testbatch/<batchName>')
    def curator_app_performance_test(batchName):
        curator_app_endpoint = os.getenv("CURATOR_APP_ENDPOINT")
        url = os.path.join(curator_app_endpoint, "runTest", batchName)
        result = {"num_failed": 0, "tests_failed": [], "info": {}}
        app.logger.debug("Calling {}".format(url))
        response = requests.get(url, verify=False)
        app.logger.debug("RESPONSE")
        app.logger.debug(response)
        json_response = response.json()
        if json_response["status"] != "success":
            result["num_failed"] = 1
            result["tests_failed"].append("Curator App testing batch " + batchName)
            return json.dumps(result)
        
        result["info"]["Curator App Performance Test: "+batchName] = {"status_code": response.status_code}

        return json.dumps(result)

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
        app.logger.debug(
            "checking dir: " + base_dropbox_path + "/" + dataverse_dropbox + "/" + "incoming" + "/" + batchName)
        if os.path.exists(os.path.join(base_dropbox_path, dataverse_dropbox, "incoming", batchName)):
            dataset_transferred = True
            result["info"]["Dropbox Transfer Status"] = {
                "Found Dataset at Path": str(os.path.join(base_dropbox_path, dataverse_dropbox, "incoming", batchName))}

        if not dataset_transferred:
            result["num_failed"] += 1
            result["tests_failed"].append("Check Dropbox Transfer")
            result["Failed Dropbox Transfer"] = {
                "Dropbox Transfer Status": "Could not find " + batchName + " in dropbox " + os.path.join(
                    base_dropbox_path, dataverse_dropbox)}

        return json.dumps(result)

    @app.route('/ingest/deleteFromDropbox/<batchName>')
    def ingest_delete_from_dropbox(batchName):
        num_failed_tests = 0
        tests_failed = []
        result = {"num_failed": num_failed_tests, "tests_failed": tests_failed, "info": {}}

        app.logger.debug("Delete test dataset from dropbox")
        if shutil.rmtree(os.path.join(base_dropbox_path, dataverse_dropbox, "incoming", batchName)):
            result["info"]["Delete Dataset From Dropbox"] = {
                "Deleted Dataset at Path": str(
                    os.path.join(base_dropbox_path, dataverse_dropbox, "incoming", batchName))}
        else:
            result["num_failed"] += 1
            result["tests_failed"].append("Delete Dataset From Dropbox")
            result["Failed Delete From Dropbox"] = {"Delete From Dropbox": "Could not delete " +
                                                                           batchName + "in dropbox " + os.path.join(
                base_dropbox_path, dataverse_dropbox)}
        return json.dumps(result)

    def _build_drs_admin_md_for_documentation(source_path, osn_unique_appender):
        
        thesis_name = "0521Yolandayuanlupeng_finalNaming Expeditor.pdf"
        license_name = "setup_2E592954-F85C-11EA-ABB1-E61AE629DA94.pdf"
        
        file_info = {
            thesis_name: {
                "modified_file_name":
                "Thesis.pdf",
                "object_role": "THESIS",
                "object_osn": "ETD_THESIS_DAIS_test_"
                + osn_unique_appender,
                "file_osn": "ETD_THESIS_DAIS_test_"
                + osn_unique_appender + "_1"
            },
            license_name: {
                "modified_file_name":
                "License.pdf",
                "object_role": "LICENSE",
                "object_osn": "ETD_LICENSE_DAIS_test_"
                + osn_unique_appender,
                "file_osn": "ETD_LICENSE_DAIS_test_"
                + osn_unique_appender + "_1"
            },
            "mets.xml": {
                "modified_file_name": "mets.xml",
                "object_role": "DOCUMENTATION",
                "object_osn": "ETD_DOCUMENTATION_DAIS_test_"
                + osn_unique_appender,
                "file_osn": "ETD_DOCUMENTATION_DAIS_test_"
                + osn_unique_appender + "_1"
            }
        }
        payload_data = {"package_id": "ETD_TESTING_" + osn_unique_appender,
                        "fs_source_path": source_path,
                        "s3_path": "",
                        "s3_bucket_name": "",
                        "depositing_application": "ETD",
                        "admin_metadata": {
                            "depositingSystem": "ETD",
                            "ownerCode": "HUL.TEST",
                            "billingCode": "HUL.TEST.BILL_0001",
                            "urnAuthorityPath": "HUL.TEST",
                            "original_queue": "test",
                            'task_name': "test",
                            "retry_count": 0,
                            "mmsid": "12345",
                            "dash_id": "TEST1234",
                            "pq_id": "PQ-30522803",
                            "alma_id": "99156631569803941",
                            "file_info": file_info
                        }
                        }
        return payload_data
    
    def _call_dims_api(payload_data): # pragma: no cover, no calling dims for testing # noqa
        dims_endpoint = os.getenv('DIMS_ENDPOINT') + '/ingest'

        app.logger.debug("DIMS endpoint: {}".format(dims_endpoint))

        # Call DIMS ingest
        ingest_etd_export = None

        jwt_private_key_path = os.getenv('DIMS_PRIVATE_KEY')
        try:
            with open(jwt_private_key_path) as jwt_private_key_file:
                jwt_private_key = jwt_private_key_file.read()
        except Exception:
            msg = "Error opening private jwt token."
            raise Exception(msg)

        jwt_expiration = int(os.getenv('JWT_EXPIRATION', 1800))
        # calculate iat and exp values
        current_datetime = datetime.now()
        current_epoch = int(current_datetime.timestamp())
        expiration = current_datetime + timedelta(seconds=jwt_expiration)
        app.logger.debug("expiration: {}".format(expiration))

        # generate JWT token
        request_body = jcs.canonicalize(payload_data).decode("utf-8")
        body_hash = hashlib.sha256(request_body.encode()).hexdigest()
        jwt_token = jwt.encode(
            payload={'iss': 'DAIS_int_test', 'iat': current_epoch,
                     'bodySHA256Hash': body_hash,
                     'exp': int(expiration.timestamp())},
            key=jwt_private_key,
            algorithm='RS256',
            headers={"alg": "RS256", "typ": "JWT", "kid": "defaultDaisIntTest"}
        )

        headers = {"Authorization": "Bearer " + jwt_token}

        app.logger.debug("Payload Data: {}".format(payload_data))
        ingest_etd_export = requests.post(
            dims_endpoint,
            headers=headers,
            json=payload_data,
            verify=False)

        json_ingest_response = ingest_etd_export.json()
        if json_ingest_response["status"] == "failure":
            raise Exception("DIMS Ingest call failed")
        return json_ingest_response