import os
from flask import Flask

# Import custom modules from the local project
# Import API resources
from . import resources

# App factory
def create_app():
  # Create and configure the app
  app = Flask(__name__, instance_relative_config=True)
  # App config
  app.config.from_mapping(
      ROOT_ROUTE = '/'
  )

  # App logger
  app.logger.setLevel(os.environ.get('APP_LOG_LEVEL', 'INFO'))

  # Resources
  resources.define_resources(app)

  return app
