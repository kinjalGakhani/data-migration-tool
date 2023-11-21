import json
import os
import time
import uuid
from pathlib import Path

from google.cloud import bigquery, storage
from googleapiclient.discovery import build
from google.cloud import bigquery_datatransfer
from jinja2 import Environment, FileSystemLoader
from test_utils import parse_config


# Load integration test ddl/sql/data config file in DMT gcs config bucket
def load_test_config(config_file, config, uniq_id, type):
    env = Environment(loader=FileSystemLoader("src/tests/end_to_end/config"))
    config_template = env.get_template(config_file)
    print(config_file)

    datasource_name = config_file.split("/")[len(config_file.split("/")) - 2]

    rendered_config = config_template.render(
        project_id=PROJECT_ID,
        unique_id=uniq_id + "_" + type,
        bucket_name=TRANSLATION_BUCKET_NAME,
        config_bucket_name=CONFIG_BUCKET_NAME,
        source_ip=(
            os.getenv(config["SOURCE_IP"].split("ENV-")[1])
            if config["SOURCE_IP"].startswith("ENV-")
            else config["SOURCE_IP"]
        )
        if "SOURCE_IP" in config
        else "",
        source_schema=(
            os.getenv(config["SOURCE_SCHEMA"].split("ENV-")[1])
            if config["SOURCE_SCHEMA"].startswith("ENV-")
            else config["SOURCE_SCHEMA"]
        )
        if "SOURCE_SCHEMA" in config
        else "",
        target_schema=get_target_datasource_name(datasource_name, uniq_id),
        source_username=(
            os.getenv(config["SOURCE_USERNAME"].split("ENV-")[1])
            if config["SOURCE_USERNAME"].startswith("ENV-")
            else config["SOURCE_USERNAME"]
        )
        if "SOURCE_USERNAME" in config
        else "",
        secret_name=config["SECRET_NAME"] if "SECRET_NAME" in config else "",
        source_dbname=(
            os.getenv(config["SOURCE_DBNAME"].split("ENV-")[1])
            if config["SOURCE_DBNAME"].startswith("ENV-")
            else config["SOURCE_DBNAME"]
        )
        if "SOURCE_DBNAME" in config
        else "",
        validation_mode=config["VALIDATION_MODE"]
        if "VALIDATION_MODE" in config
        else "",
        validation_type=config["VALIDATION_TYPE"]
        if "VALIDATION_TYPE" in config
        else "",
        validation_mapping_file=config["VALIDATION_MAPPING_FILE"]
        if "VALIDATION_MAPPING_FILE" in config
        else "",
        data_mig_table_list_file=config["DATA_MIG_TABLE_LIST_FILE"]
        if "DATA_MIG_TABLE_LIST_FILE" in config
        else "",
        data_bucket_name=DATA_FILE_BUCKET_NAME,
    )

    print(config)

    config_file_name = (
        (
            config_file.split(".")[0]
            + "_"
            + config["VALIDATION_MODE"]
            + "."
            + config_file.split(".")[1]
        )
        if (config["VALIDATION_MODE"] is not None)
        else config_file
    )
    print(config_file_name)
    storage_client.bucket(CONFIG_BUCKET_NAME).blob(config_file_name).upload_from_string(
        rendered_config
    )
    print(rendered_config)


# Load test data in DMT cloud storage bucket
def load_test_data(unique_generated_id: str):
    print("Loading test data")
    bucket = storage_client.bucket(TRANSLATION_BUCKET_NAME)

    for sql_file in Path(".").glob("src/tests/end_to_end/input/**/*.sql"):
        bucket.blob(
            str(sql_file).split("end_to_end/")[
                len(str(sql_file).split("end_to_end/")) - 1
            ]
        ).upload_from_filename(sql_file)

    data_file_bucket = storage_client.bucket(DATA_FILE_BUCKET_NAME)
    for csv in Path(".").glob("src/tests/end_to_end/files/**/*.csv"):
        data_file_bucket.blob(
            str(csv).split("end_to_end/")[len(str(csv).split("end_to_end/")) - 1]
        ).upload_from_filename(csv)

    config_bucket = storage_client.bucket(CONFIG_BUCKET_NAME)

    for csv in Path(".").glob("src/tests/end_to_end/validation/**/*.csv"):
        text = replace_string_in_csv(csv, unique_generated_id)
        config_bucket.blob(
            str(csv).split("end_to_end/")[len(str(csv).split("end_to_end/")) - 1]
        ).upload_from_string(text)


# Configure/replace target datasource string in validation csv file
def replace_string_in_csv(csv_file_name, str_to_replace):
    text = open(csv_file_name, "r")

    # join() method combines all contents of csvfile.csv and formed as a string
    text = "".join([i for i in text])

    # search and replace the contents
    text = text.replace("<target_schema_unique_id>", str_to_replace)

    return text


# Delete running DTS jobs if any for clean run
def delete_transfer_configs():

    transfer_client = bigquery_datatransfer.DataTransferServiceClient()

    # [START bigquerydatatransfer_list_configs]
    parent = transfer_client.common_project_path(PROJECT_ID)
# parent = transfer_client.common_project_path("pso-data-migration-tool-test")
    configs = transfer_client.list_transfer_configs(parent=parent)
    print("Got the following configs:")
    for config in configs:
        print(f"\tID: {config.name}")
        # [START bigquerydatatransfer_delete_transfer]
        transfer_client.delete_transfer_config(name=config.name)
        
    # bq_data_transfer_client = build("bigquerydatatransfer", "v1")
    # transferConfigs = (
    #     bq_data_transfer_client.projects()
    #     .transferConfigs()
    #     .list(parent=f"projects/{PROJECT_ID}", pageSize=1000)
    #     .execute()
    #     .get("transferConfigs")
    # )
    # if transferConfigs:
    #     for transferConfig in transferConfigs:
    #         response = (
    #             bq_data_transfer_client.projects()
    #             .locations()
    #             .transferConfigs()
    #             .delete(
    #                 name=transferConfig.get("name"),
    #             )
    #             .execute()
    #         )
    #         return response


# Prepare and get target BigQuery datasource name
def get_target_datasource_name(datasource, unique_id):
    return datasource + "_" + unique_id


# Replace unique id hyphen with underscore as per BQ naming convention
def get_replaced_unique_id(unique_id):
    return unique_id.replace("-", "_")


# Delete created BQ dataset if exist
def delete_bq_dataset(unique_id):
    client = bigquery.Client()

    datasources = ["oracle", "teradata"]

    for datasource in datasources:
        client.delete_dataset(
            get_target_datasource_name(datasource, unique_id),
            delete_contents=True,
            not_found_ok=True,
        )  # Make an API request.


# Run the following to setup project
"""
gcloud config set project YOUR_PROJECT_ID &&
bash iam-setup.sh &&
gcloud builds submit . --config cloudbuild_deploy.yaml --substitutions _DATA_SOURCE="teradata"
"""


cfg = parse_config("src/tests/end_to_end/input.properties")

PROJECT_ID = os.getenv("PROJECT_ID")

CONFIG_BUCKET_NAME = cfg.get("inputs", "CONFIG_BUCKET_NAME")
CONFIG_BUCKET_NAME = CONFIG_BUCKET_NAME.replace("<PROJECT_ID>", PROJECT_ID)

TRANSLATION_BUCKET_NAME = cfg.get("inputs", "TRANSLATION_BUCKET_NAME")
TRANSLATION_BUCKET_NAME = TRANSLATION_BUCKET_NAME.replace("<PROJECT_ID>", PROJECT_ID)

DATA_FILE_BUCKET_NAME = cfg.get("inputs", "DATA_FILE_BUCKET_NAME")
DATA_FILE_BUCKET_NAME = DATA_FILE_BUCKET_NAME.replace("<PROJECT_ID>", PROJECT_ID)

# print(f'{cfg.options("inputs")}, {CONFIG_BUCKET_NAME} and {TRANSLATION_BUCKET_NAME} and {DATA_FILE_BUCKET_NAME}')
storage_client = storage.Client(project=PROJECT_ID)

unique_generated_id = get_replaced_unique_id(os.getenv("BUILD_ID", str(uuid.uuid4())))

print(f"unique identifier {unique_generated_id}")

load_test_data(unique_generated_id)

print("Upload DDL config files")
ddl_config_list = cfg.get("inputs", "DDL_CONFIG_LIST")
ddl_config_list_obj = json.loads(ddl_config_list)
for ddl_config_file in ddl_config_list_obj:
    for ddl_config_item in ddl_config_list_obj[ddl_config_file]:
        load_test_config(ddl_config_file, ddl_config_item, unique_generated_id, "ddl")
        time.sleep(120)  # Delay for 2 minute (120 seconds).

print("Delete data transfer configs")
delete_transfer_configs()

print("Upload data migration config files")
data_config_list = cfg.get("inputs", "DATA_CONFIG_LIST")

data_config_list_obj = json.loads(data_config_list)

for data_config_file in data_config_list_obj:
    for data_config_item in data_config_list_obj[data_config_file]:
        load_test_config(
            data_config_file, data_config_item, unique_generated_id, "data"
        )  # First set up tables via DDLs
        time.sleep(120)  # Delay for 2 minute (120 seconds).

time.sleep(660)  # Delay for 11 minute (660 seconds) for data-migration completion
print("Upload SQL config files")
sql_config_list = cfg.get("inputs", "SQL_CONFIG_LIST")

sql_config_list_obj = json.loads(sql_config_list)

for sql_config_file in sql_config_list_obj:
    for sql_config_item in sql_config_list_obj[sql_config_file]:
        load_test_config(
            sql_config_file, sql_config_item, unique_generated_id, "sql"
        )  # First set up tables via DDLs
        time.sleep(120)  # Delay for 2 minute (120 seconds).

time.sleep(300)  # Delay for 5 minute (300 seconds).
print("Delete BQ dataset")
delete_bq_dataset(unique_generated_id)
print("Finished...")
