#!/usr/local/bin/python

"""
An example task that extracts data from a PostgreSQL database,
and loads it into Snowflake. It also uses CloudReactor's status_updater
module to send custom status messages. These messages are visible on the
CloudReactor dashboard. Immediately below are the key variables to change.
"""
from typing import Any, Dict, Optional, Tuple

import csv
import gzip
import json
import logging
import os
from pathlib import Path
from urllib.parse import quote
import shutil
# Load the .env file (or .env.dev in development) into environment variables
from dotenv import load_dotenv

# for writing gzipped CSVs
import psycopg2
# RealDictCursor allows us to fetch columns by name
from psycopg2.extras import RealDictCursor
from psycopg2 import OperationalError
from psycopg2 import sql
import snowflake.connector
from status_updater import StatusUpdater


# -- (> ------------------ SECTION: key variables to change ------------------

# Define destination table schema here.
# This destination schema MUST match the order and name of the table retrieved
# from Postgres below. Unfortunately this has to be manual because each
# column's data type must also be set.
# Each element in "TABLE_COLS" has shape: "column_name": "snowflake_data_type"
# Data type list:
# https://docs.snowflake.com/en/sql-reference/intro-summary-data-types.html
# Example below imagines a source table containing records of movie rentals

TABLE_COLS = {
    "rental_id": "INT",
    "rental_date": "TIMESTAMP_NTZ",
    "inventory_id": "INT",
    "customer_id": "INT",
    "return_date": "TIMESTAMP_NTZ",
    "staff_id": "INT",
    "last_update": "TIMESTAMP_NTZ"
}

# Set "last_updated_column_name" to the column in your source table that
# records the last updated timestamp. Since the source table columns should
# be listed above, this should also match one of the keys above
LAST_UPDATED_COLUMN_NAME = 'last_update'

# Select which key from TABLE_COLS should be the unique key (used for upsert
# into Snowflake)
UNIQUE_KEY = 'rental_id'

# Define which postgres table to replicate
SOURCE_TABLE = 'rental'

# Define the Snowflake warehouse, database, schema and table to load data into
SNOWFLAKE_WAREHOUSE = "tiny_warehouse_mg"
SNOWFLAKE_DB = "rental"
SNOWFLAKE_SCHEMA = "rentalschema"
SNOWFLAKE_TABLE = "rental"

# Define name of Snowflake table where "last_updated_column_name" timestamp
# and ID will be saved. These are used to identify which records in Postgres
# are new / updated. This table name should not conflict with any other table.
ETL_STATUS_TABLE_NAME = "etl_status"

# "DEBUG_MODE = True" logs additional info e.g. programmatically built
# query strings
DEBUG_MODE = True

# Set CSV filename where new / updated records will be written before
# uploading to Snowflake
TMP_FILE_DIR = os.environ.get('TEMP_FILE_DIR', '/tmp').rstrip('/')
FILENAME = f"{TMP_FILE_DIR}/postgres_records_to_load.csv"

# Set number of records to fetch from Postgres and upload to Snowflake per loop
# Snowflake recommends *compressed* files between 10MB-100MB. See:
# https://docs.snowflake.com/en/user-guide/data-load-considerations-prepare.html#general-file-sizing-recommendations
NUM_RECORDS = 200000

# -- <) ---------------------------- END_SECTION ----------------------------

def main():
    """
    Connect to Postgres (source) and Snowflake (destination). Retrieve data
    from source, upload to Snowflake staging, and load into Snowflake
    """

    load_dotenv()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s: %(message)s")


    with StatusUpdater() as updater, \
        make_pg_connection(updater) as pg_conn, \
        make_snowflake_connection(updater) as snowflake_conn:

        # create Snowflake warehouse, db, schema, ETL status tracking table,
        # stage and file format
        create_snowflake_infra(snowflake_conn, updater)

        # programmatically create queries to create destination table
        # and load files from stage into destination table
        load_file_query, create_dest_table_query = \
            create_snowflake_queries()

        # create destination table
        exec_snowflake_query(snowflake_conn,
                             create_dest_table_query,
                             updater,
                             'Successfully created destination table')

        loop_num = 1
        success_count = 0
        finished = False

        while not finished:
            logging.info('Fetching data from Postgres')
            logging.info("Loop #: %s", loop_num)

            # Fetch data from Postgres, write to CSV, gzip
            # finished = True if this is last loop, False otherwise
            row_count = source_data_to_stage(snowflake_conn, pg_conn, updater)

            finished = (row_count < NUM_RECORDS)

            success_count += row_count

            logging.info("Finished fetching data from Postgres: %s", finished)

            # Load file from stage into final Snowflake table
            stage_to_snowflake(snowflake_conn, updater, load_file_query)
            loop_num += 1

            updater.send_update(success_count=success_count)



def make_pg_connection(updater: StatusUpdater):
    """
    Returns a connection to a PostgreSQL database
    """
    postgres_secrets = os.environ.get('POSTGRES_SECRETS')
    # convert secrets string to dictionary
    pg_secrets_dict = json.loads(postgres_secrets)
    db_name = pg_secrets_dict['dbname']
    db_user = pg_secrets_dict['username']
    db_password = pg_secrets_dict['password']
    db_host = pg_secrets_dict['host']
    db_port = int(pg_secrets_dict.get('port', '5432'))

    connection = None
    try:
        connection = psycopg2.connect(
            database=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port,
            cursor_factory=RealDictCursor
        )

        # send + print success message
        msg = 'Connection to PostgreSQL DB succeeded'
        updater.send_update(last_status_message=msg)
        logging.info(msg)

    except OperationalError as e:
        logging.exception('Failed to connect to PostgreSQL DB')
        updater.send_update(last_status_message=f"The error '{e}' occurred")
        raise e

    return connection

def make_snowflake_connection(updater: StatusUpdater):
    """
    Returns a connection to Snowflake account
    """
    snowflake_secrets = os.environ.get('SNOWFLAKE_SECRETS')
    # convert secrets string to dictionary
    snowflake_secrets_dict = json.loads(snowflake_secrets)
    user = snowflake_secrets_dict['user']
    password = snowflake_secrets_dict['password']
    account = snowflake_secrets_dict['account']

    snowflake.connector.paramstyle = 'qmark'

    try:
        connection = snowflake.connector.connect(
            user=user,
            password=password,
            account=account
            )

        # send + print success message
        msg = "Connection to Snowflake successful"
        updater.send_update(last_status_message=msg)
        logging.info(msg)
        return connection
    except snowflake.connector.errors.ProgrammingError as e:
        logging.exception('Failed to connect to Snowflake')
        raise e


def exec_snowflake_query(snowflake_conn, query: str, updater: StatusUpdater,
        success_msg: Optional[str] = None) -> None:
    """Creates a Snowflake cursor and executes a query on that cursor"""
    with snowflake_conn.cursor() as cur:
        try:
            cur.execute(query)

            # send + print success message
            if success_msg:
                updater.send_update(last_status_message=success_msg)
                logging.info(success_msg)

        except snowflake.connector.errors.ProgrammingError as e:
            logging.exception("Failed to execute Snowflake query")
            raise e

def create_snowflake_infra(snowflake_conn, updater: StatusUpdater) -> None:
    """
    Creates Snowflake warehouse, db, schema, ETL status tracking table,
    stage and file format.
    """
    create_wh = f"CREATE WAREHOUSE IF NOT EXISTS {SNOWFLAKE_WAREHOUSE}"
    create_db = f"CREATE DATABASE IF NOT EXISTS {SNOWFLAKE_DB}"
    use_db = f"USE DATABASE {SNOWFLAKE_DB}"
    create_schema = f"CREATE SCHEMA IF NOT EXISTS {SNOWFLAKE_SCHEMA}"
    use_schema = f"USE SCHEMA {SNOWFLAKE_DB}.{SNOWFLAKE_SCHEMA}"

    # The ETL status tracking table lists, for each replicated table, the name
    # of the "last_updated" column (may simply be "last_updated") and the
    # last_updated timestamp.
    # This table determines which new records to retrieve and then stage.
    create_tracking_table = f"""
        CREATE TABLE IF NOT EXISTS {ETL_STATUS_TABLE_NAME} (
            table_name VARCHAR(50),
            column_name VARCHAR(50),
            last_value TIMESTAMP_NTZ,
            last_updated_id INT)
        """

    create_file_format = f"""
        CREATE OR REPLACE FILE FORMAT {SNOWFLAKE_TABLE}_format
        TYPE = 'csv'
        COMPRESSION = 'GZIP'
        SKIP_HEADER = 1;
        """

    create_stage = f"""create or replace stage {SNOWFLAKE_TABLE}_stage
        file_format = {SNOWFLAKE_TABLE}_format
        """

    exec_snowflake_query(snowflake_conn,
                         create_wh,
                         updater,
                         'Created warehouse')
    exec_snowflake_query(snowflake_conn,
                         create_db,
                         updater,
                         'Created database')
    exec_snowflake_query(snowflake_conn,
                         use_db,
                         updater,
                         'Using database')
    exec_snowflake_query(snowflake_conn,
                         create_schema,
                         updater,
                         'Created schema')
    exec_snowflake_query(snowflake_conn,
                         use_schema,
                         updater,
                         'Using schema')
    exec_snowflake_query(snowflake_conn,
                         create_tracking_table,
                         updater,
                         'Created ETL status tracking table')
    exec_snowflake_query(snowflake_conn,
                         create_file_format,
                         updater,
                         'Created file format')
    exec_snowflake_query(snowflake_conn,
                         create_stage,
                         updater,
                         'Created stage')

def create_snowflake_queries() -> Tuple[str, str]:
    """
    Programmatically builds "create table" and "merge" queries.
    This is used when loading data from Snowflake stage to destination table.
    """
    # create join clause using unique key
    join_on_unique_key = f"(dest.{UNIQUE_KEY} = stg.{UNIQUE_KEY})\n"

    max_col_index = len(TABLE_COLS)-1
    create_dest_table_query = f"CREATE TABLE IF NOT EXISTS {SNOWFLAKE_TABLE} (\n"
    select_query = 'select '
    when_not_matched_query = ' ('
    when_not_matched_query_values = ' ('

    for index, key in enumerate(TABLE_COLS):
        # loop through TABLE_COLS and build all the sub-queries that are
        # based on this.

        # Column names do not exist in staging. Therefore need to explicitly
        # retrieve columns with "$1, $2" etc. col_num defines this.
        col_num = index + 1

        create_dest_table_query += f"{key} {TABLE_COLS[key]}"
        select_query += f"${col_num} {key}"
        when_not_matched_query += key
        when_not_matched_query_values += f"stg.{key}"

        if index < max_col_index:
            create_dest_table_query += ','
            select_query += ','
            when_not_matched_query += ','
            when_not_matched_query_values += ','

    create_dest_table_query += ')'
    select_query += f" from @{SNOWFLAKE_TABLE}_stage"
    when_not_matched_query += ')'
    when_not_matched_query_values += ')'

    # build "when matched..." query using dictionary that excludes unique key
    when_matched_query = build_when_matched_query()

    load_file_query = f"""
        merge into {SNOWFLAKE_TABLE} as dest using
            (
                {select_query}
            ) as stg on {join_on_unique_key}
        when matched then update set
            {when_matched_query}
        when not matched then insert
            {when_not_matched_query}
        values
            {when_not_matched_query_values};
    """

    # print all programmatically created query strings
    if DEBUG_MODE:
        logging.info("--------- BEGIN: programmatically created queries -----")
        logging.info("create_dest_table_query: \n%s", create_dest_table_query)
        logging.info("select_query: \n%s", select_query)
        logging.info("join_on_unique_key: \n%s", join_on_unique_key)
        logging.info("when_matched_query: \n%s", when_matched_query)
        logging.info("when_not_matched_query: \n%s", when_not_matched_query)
        logging.info("when_not_matched_query_values: \n%s",
                     when_not_matched_query_values)
        logging.info("complete load_file query: \n%s", load_file_query)
        logging.info("------------------------- END -------------------------")

    return (load_file_query, create_dest_table_query)

def source_data_to_stage(snowflake_conn, pg_conn, updater: StatusUpdater) -> int:
    """
    Use last_updated to fetch new + updated records from PostgreSQL.
    Write these records to CSV, gzip, upload to snowflake staging.
    Return the count of the rows successfully loaded.
    """
    # get last-updated date from ETL status tracking table (in Snowflake)
    last_updated = get_last_updated(snowflake_conn)

    # retrieve records from postgres, save as tmp csv
    row_count = get_records(pg_conn, updater, last_updated)

    if row_count > 0:
        # at least one record pulled from postgres
        gzip_file()

        # put file to Snowflake stage
        stage_file(snowflake_conn, updater)

    return row_count

def get_last_updated(snowflake_conn) -> Optional[Dict[str, Any]]:
    """
    Gets last-updated date & ID from snowflake ETL status tracking table
    Returns "None" if doesn't exist
    """

    # identifier(?) allows binding of table name
    get_last_updated_query = """
        SELECT last_value, last_updated_id
        from identifier(?)
        where table_name = ?
        """

    with snowflake_conn.cursor() as cur:
        try:
            cur.execute(get_last_updated_query,
                        (ETL_STATUS_TABLE_NAME, SNOWFLAKE_TABLE))
            logging.info("""Fetching last updated info from
                ETL status tracking table
                """)
            record = cur.fetchone()
            logging.info('Timestamp & id of most-recently uploaded record:')
            logging.info(record)

            last_updated = None
            if record is None:
                logging.info('ETL status tracking table: no record found')
            else:
                last_updated = {
                    'timestamp': record[0],
                    'id': record[1],
                }
                logging.info("ETL status tracking table: max last_updated: %s",
                    last_updated['timestamp'])
                logging.info("""ETL status tracking table: max id associated
                    with last_updated timestamp: %s""", last_updated['id'])

            return last_updated
        except snowflake.connector.errors.ProgrammingError as e:
            logging.exception("Failed to execute Snowflake query")
            raise e

def get_records(pg_conn, updater: StatusUpdater, last_updated):
    """
    Retrieves records from Postgres. Writes CSV to tmp dir.
    """
    if last_updated is None:
        sql_query = sql.SQL("""
            COPY (
                select *
                from {source_table}
                order by {last_updated_column} asc, {unique_key} asc
                limit {num_records}
            ) TO STDOUT WITH CSV HEADER
            """).format(
                source_table=sql.Identifier(SOURCE_TABLE),
                last_updated_column=sql.Identifier(LAST_UPDATED_COLUMN_NAME),
                unique_key=sql.Identifier(UNIQUE_KEY),
                num_records=sql.Literal(NUM_RECORDS)
            )
    else:
        # where clause has two parts
        # 1. First part gets records with the same timestamp but different id
        # to what's already in snowflake.
        # 2. Second part gets records with > timestamp (ID doesn't matter).
        # Together, these grab all new / updated records
        sql_query = sql.SQL("""
            COPY (
                select *
                from {source_table}
                where (
                    (({last_updated_column} = {last_updated}) and ({unique_key} > {id}))
                    or ({last_updated_column} > {last_updated})
                    )
                order by {last_updated_column} asc, {unique_key} asc
                limit {num_records}
            ) TO STDOUT WITH CSV HEADER
            """).format(
                source_table=sql.Identifier(SOURCE_TABLE),
                last_updated_column=sql.Identifier(LAST_UPDATED_COLUMN_NAME),
                unique_key=sql.Identifier(UNIQUE_KEY),
                last_updated=sql.Literal(last_updated["timestamp"]),
                id=sql.Literal(last_updated["id"]),
                num_records=sql.Literal(NUM_RECORDS)
            )

    with pg_conn.cursor() as pg_cur, open(FILENAME, 'w') as f:
        pg_cur.copy_expert(sql_query, f)
        row_count = pg_cur.rowcount
        logging.info("COPY row count from Postgres: %s", row_count)

    # confirm contents look as expected: print first 5 lines
    if DEBUG_MODE:
        show_csv_file()

    updater.send_update(last_status_message='Copied from PG to CSV')

    return row_count

def gzip_file() -> None:
    """
    gzips FILENAME
    """
    with open(FILENAME, 'rb') as f_in, \
        gzip.open(f'{FILENAME}.gz', 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)

    # confirm gzipped file exists
    if DEBUG_MODE:
        logging.info("Confirming gzipped file exists: %s",
                     Path(f"{FILENAME}.gz").stat())

def stage_file(snowflake_conn, updater: StatusUpdater) -> None:
    """
    Puts file from local tmp dir to Snowflake stage
    """

    filename_url_encoded = 'file://' + quote(f"{FILENAME}.gz")

    # if want to use files elsewhere (e.g. athena), put data to external stage
    stage_file_query = f"""
        put {filename_url_encoded}
        @{SNOWFLAKE_TABLE}_stage
        """

    exec_snowflake_query(snowflake_conn,
                         stage_file_query,
                         updater,
                         f"""Put file {filename_url_encoded}
                         to Snowflake staging
                         """)

    # confirm that data has been loaded into staging by printing
    # a couple of columns
    if DEBUG_MODE:
        verify_snowflake_staging(snowflake_conn)

def show_csv_file() -> None:
    """
    Output the first 5 lines of the CSV produced by Postgres.
    """
    logging.info("CSV file: first five lines:")
    with open(FILENAME) as csv_file:
        csv_reader = csv.reader(csv_file)
        line_count = 0
        for row in csv_reader:
            if line_count >= 5:
                break
            logging.info(row)
            line_count += 1

def verify_snowflake_staging(snowflake_conn):
    """
    Prints first five records from the first two columns from stage,
    to confirm file has uploaded to Snowflake stage correctly
    """
    with snowflake_conn.cursor() as cur:
        cur.execute(f"""select $1, $2
            from @{SNOWFLAKE_TABLE}_stage
            (file_format => {SNOWFLAKE_TABLE}_format)
            """)
        rows = cur.fetchmany(5)
        try:
            if not rows:
                raise RuntimeError('No rows in staging file')

            for row in rows:
                logging.info(row)
        except Exception as e:
            logging.error('Verification of file in Snowflake stage failed')
            raise e

def stage_to_snowflake(snowflake_conn, updater: StatusUpdater,
        load_file_query: str) -> None:
    """
    Inserts new / updated records into destination table. If succeeds, updates
    ETL status tracking table and removes files from stage
    """

    # load file into destination table; if succeeds, update ETL status
    # tracking table and clean up staging
    try:
        success_msg = f"""
            Loaded data from staging into Snowflake table
            '{SNOWFLAKE_TABLE}'
            """

        # upsert data into destination (dest) table from staging (stg)
        # https://support.snowflake.net/s/article/how-to-perform-a-mergeupsert-from-a-flat-file-staged-on-s3
        exec_snowflake_query(snowflake_conn,
                             load_file_query,
                             updater,
                             success_msg)

        # Grab last updated timestamp and max(ID) associated with that.
        # Insert into snowflake ETL status tracking table
        store_last_updated = f"""
            merge into {ETL_STATUS_TABLE_NAME} as dest using
            (
                select
                    '{SNOWFLAKE_TABLE}' as table_name,
                    '{LAST_UPDATED_COLUMN_NAME}' as column_name,
                    max({LAST_UPDATED_COLUMN_NAME}) as last_value,
                    (select max({UNIQUE_KEY})
                        from {SNOWFLAKE_TABLE}
                        where {LAST_UPDATED_COLUMN_NAME} =
                            (select max({LAST_UPDATED_COLUMN_NAME})
                            from {SNOWFLAKE_TABLE})) as last_updated_id
                from {SNOWFLAKE_TABLE}
            ) as source on (dest.table_name = source.table_name)
            when matched then
                update set
                    dest.table_name = source.table_name,
                    dest.column_name = source.column_name,
                    dest.last_value = source.last_value,
                    dest.last_updated_id = source.last_updated_id
            when not matched then
                insert (
                    table_name,
                    column_name,
                    last_value,
                    last_updated_id)
                values (
                    source.table_name,
                    source.column_name,
                    source.last_value,
                    source.last_updated_id);
            """

        logging.info("Storing last_updated: %s", store_last_updated)
        exec_snowflake_query(snowflake_conn,
                             store_last_updated,
                             updater,
                             """Stored last_updated value &
                             id in ETL status tracking table""")

        # Clean up stage
        remove_stage_query = f"""
            remove @{SNOWFLAKE_TABLE}_stage
            """
        exec_snowflake_query(snowflake_conn,
                             remove_stage_query,
                             updater,
                             'Removed stage')

    except snowflake.connector.errors.ProgrammingError as e:
        logging.exception('Failed to execute Snowflake query')
        raise e

def build_when_matched_query() -> str:
    """
    The "when matched ..." portion of the Snowflake "MERGE" query requires
    columns excluding the unique key column. This function builds that query,
    using a dictionary that contains all table columns except the unique key.
    """

    # Create copy of dictionary, remove unique key
    table_cols_excl_unique_key = TABLE_COLS.copy()
    del table_cols_excl_unique_key[UNIQUE_KEY]

    # print column dictionaries for debugging.
    if DEBUG_MODE:
        logging.info("TABLE_COLS: \n%s", TABLE_COLS)
        logging.info("table_cols_excl_unique_key: %s",
                     table_cols_excl_unique_key)

    # need to know total items in dictionary in order to detect last item
    max_col_index = len(table_cols_excl_unique_key) - 1

    # programmatically build "when matched..." query clause
    when_matched_query = ''
    for index, key in enumerate(table_cols_excl_unique_key):
        when_matched_query += f"dest.{key} = stg.{key}"

        if index < max_col_index:
            # not at last element; add trailing comma
            when_matched_query += ','

    return when_matched_query

if __name__ == '__main__':
    main()
