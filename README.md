# dais-integration-tests
This project will run the integration tests for the DAIS project

The project has the following endpoints available:

* An API description that displays here: http://localhost:10582/
* An API endpoint that displays the version here: http://localhost:10582/version
* A Readiness page here: http://localhost:10582/readiness

## Technology Stack
##### Language
Python

##### Framework
Flask

##### Development Operations
Docker Compose

## Local Development Environment Setup Instructions

### 1: Clone the repository to a local directory
```git clone git@github.com:harvard-lts/dais-integration-tests.git```

### 2: Create app config

##### Create config file for environment variables
- Make a copy of the config example file `./env-example.txt`
- Rename the file to `.env`
- Replace placeholder values as necessary

*Note: The config file .env is specifically excluded in .gitignore and .dockerignore, since it contains credentials it should NOT ever be committed to any repository.*

##### Create webapp.conf file for environment variables
- Make a copy of the config example file `./`
- Rename the file to `webapp.conf`
- Replace placeholder values as necessary (anything localhost will be changed in a deployed environment)

*Note: The config file webapp.conf is specifically excluded in .gitignore and .dockerignore, since it can contain credentials it should NOT ever be committed to any repository.*

### 4: Start

##### START

This command builds all images and runs all containers specified in the docker-compose-local.yml configuration.

```
docker-compose -f docker-compose-local.yml up --build --force-recreate
```

### 9: Install Packages (optional)
This step is only required if additional python packages must be installed during development. Update the requirements.txt inside the container to install new python packages.

##### Run docker exec to execute a shell in the container by name

```
docker exec -it dais-integration-tests bash
```

##### Install a new pip package

Once inside the dais-integration-tests container, run the pip install command to install a new package and update the requirements text file.

```
pip install packagename && pip freeze > requirements.txt
```

### 10: Stop

##### STOP AND REMOVE

This command stops and removes all containers specified in the docker-compose-local.yml configuration. This command can be used in place of the 'stop' and 'rm' commands.

```
docker-compose -f docker-compose-local.yml down
```

