from airflow import DAG
import pandas as pd
from datetime import timedelta
from airflow.utils.dates import days_ago
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine
import psycopg2
# from airflow.operators.bash_operator import BashOperator
# from airflow.providers.postgres.operators.postgres import PostgresOperator

default_args = {
    'owner': 'Mervyn Frost',
    'start_date': days_ago(0),
    # 'email': ['mervynF@somemail.com'],
    # 'email_on_failure': True,
    # 'email_on_retry': True,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def extract(ti):
	path = "dags/uber_data.csv"
	df = pd.read_csv(path)
	ti.xcom_push(key='dataframe', value=df)

def transform(ti):
	df = ti.xcom_pull(key='dataframe')

	df['tpep_pickup_datetime'] = pd.to_datetime(df['tpep_pickup_datetime'])
	df['tpep_dropoff_datetime'] = pd.to_datetime(df['tpep_dropoff_datetime'])
	df = df.drop_duplicates().reset_index(drop=True)
	df['trip_id'] = df.index

	datetime_dim = df[['tpep_pickup_datetime','tpep_dropoff_datetime']].reset_index(drop=True)
	datetime_dim['tpep_pickup_datetime'] = datetime_dim['tpep_pickup_datetime']
	datetime_dim['pick_hour'] = datetime_dim['tpep_pickup_datetime'].dt.hour
	datetime_dim['pick_day'] = datetime_dim['tpep_pickup_datetime'].dt.day
	datetime_dim['pick_month'] = datetime_dim['tpep_pickup_datetime'].dt.month
	datetime_dim['pick_year'] = datetime_dim['tpep_pickup_datetime'].dt.year
	datetime_dim['pick_weekday'] = datetime_dim['tpep_pickup_datetime'].dt.weekday

	datetime_dim['tpep_dropoff_datetime'] = datetime_dim['tpep_dropoff_datetime']
	datetime_dim['drop_hour'] = datetime_dim['tpep_dropoff_datetime'].dt.hour
	datetime_dim['drop_day'] = datetime_dim['tpep_dropoff_datetime'].dt.day
	datetime_dim['drop_month'] = datetime_dim['tpep_dropoff_datetime'].dt.month
	datetime_dim['drop_year'] = datetime_dim['tpep_dropoff_datetime'].dt.year
	datetime_dim['drop_weekday'] = datetime_dim['tpep_dropoff_datetime'].dt.weekday


	datetime_dim['datetime_id'] = datetime_dim.index

	# datetime_dim = datetime_dim.rename(columns={'tpep_pickup_datetime': 'datetime_id'}).reset_index(drop=True)
	datetime_dim = datetime_dim[['datetime_id', 'tpep_pickup_datetime', 'pick_hour', 'pick_day', 'pick_month', 'pick_year', 'pick_weekday',
								'tpep_dropoff_datetime', 'drop_hour', 'drop_day', 'drop_month', 'drop_year', 'drop_weekday']]

	ti.xcom_push(key='datetime_dim', value=datetime_dim)

	passenger_count_dim = df[['passenger_count']].reset_index(drop=True)
	passenger_count_dim['passenger_count_id'] = passenger_count_dim.index
	passenger_count_dim = passenger_count_dim[['passenger_count_id', 'passenger_count']]

	ti.xcom_push(key='passenger_count_dim', value=passenger_count_dim)

	trip_distance_dim = df[['trip_distance']].reset_index(drop=True)
	trip_distance_dim['trip_distance_id'] = trip_distance_dim.index
	trip_distance_dim = trip_distance_dim[['trip_distance_id', 'trip_distance']]

	ti.xcom_push(key='trip_distance_dim', value=trip_distance_dim)

	rate_code_type = {
		1:"Standard rate",
		2:"JFK",
		3:"Newark",
		4:"Nassau or Westchester",
		5:"Negotiated fare",
		6:"Group ride"
	}
	rate_code_dim = df[['RatecodeID']].reset_index(drop=True)
	rate_code_dim['rate_code_id'] = rate_code_dim.index
	rate_code_dim['rate_code_name'] = rate_code_dim['RatecodeID'].map(rate_code_type)
	rate_code_dim = rate_code_dim[['rate_code_id','RatecodeID','rate_code_name']]

	ti.xcom_push(key='rate_code_dim', value=rate_code_dim)

	pickup_location_dim = df[['pickup_longitude','pickup_latitude']].reset_index(drop=True)
	pickup_location_dim['pickup_location_id'] = pickup_location_dim.index
	pickup_location_dim = pickup_location_dim[['pickup_location_id','pickup_longitude','pickup_latitude']]

	ti.xcom_push(key='pickup_location_dim', value=pickup_location_dim)

	dropoff_location_dim = df[['dropoff_longitude','dropoff_latitude']].reset_index(drop=True)
	dropoff_location_dim['dropoff_location_id'] = dropoff_location_dim.index
	dropoff_location_dim = dropoff_location_dim[['dropoff_location_id','dropoff_longitude','dropoff_latitude']]

	ti.xcom_push(key='dropoff_location_dim', value=dropoff_location_dim)

	payment_type_name = {
		1:"Credit card",
		2:"Cash",
		3:"No charge",
		4:"Dispute",
		5:"Unknown",
		6:"Voided trip"
	}
	payment_type_dim = df[['payment_type']].reset_index(drop=True)
	payment_type_dim['payment_type_id'] = payment_type_dim.index
	payment_type_dim['payment_type_name'] = payment_type_dim['payment_type'].map(payment_type_name)
	payment_type_dim = payment_type_dim[['payment_type_id','payment_type','payment_type_name']]

	ti.xcom_push(key='payment_type_dim', value=payment_type_dim)

	fact_table = df.merge(datetime_dim, left_on='trip_id', right_on='datetime_id') \
				.merge(passenger_count_dim, left_on='trip_id', right_on='passenger_count_id') \
				.merge(trip_distance_dim, left_on='trip_id', right_on='trip_distance_id') \
				.merge(rate_code_dim, left_on='trip_id', right_on='rate_code_id') \
				.merge(pickup_location_dim, left_on='trip_id', right_on='pickup_location_id') \
				.merge(dropoff_location_dim, left_on='trip_id', right_on='dropoff_location_id')\
				.merge(payment_type_dim, left_on='trip_id', right_on='payment_type_id') \
				[['trip_id','VendorID', 'datetime_id', 'passenger_count_id',
				'trip_distance_id', 'rate_code_id', 'store_and_fwd_flag', 'pickup_location_id', 'dropoff_location_id',
				'payment_type_id', 'fare_amount', 'extra', 'mta_tax', 'tip_amount', 'tolls_amount',
				'improvement_surcharge', 'total_amount']]
	
	ti.xcom_push(key='fact_table', value=fact_table)

def load(ti):
	datetime_dim = ti.xcom_pull(key='datetime_dim')
	passenger_count_dim = ti.xcom_pull(key='passenger_count_dim')
	trip_distance_dim = ti.xcom_pull(key='trip_distance_dim')
	rate_code_dim = ti.xcom_pull(key='rate_code_dim')
	pickup_location_dim = ti.xcom_pull(key='pickup_location_dim')
	dropoff_location_dim = ti.xcom_pull(key='dropoff_location_dim')
	payment_type_dim = ti.xcom_pull(key='payment_type_dim')
	fact_table = ti.xcom_pull(key='fact_table')

	engine = create_engine('postgresql+psycopg2://airflow:airflow@postgres/modeling_uber_data')
	datetime_dim.to_sql('datetime_dim', engine)	
	passenger_count_dim.to_sql('passenger_count_dim', engine)
	trip_distance_dim.to_sql('trip_distance_dim', engine)
	rate_code_dim.to_sql('rate_code_dim', engine)
	pickup_location_dim.to_sql('pickup_location_dim', engine)
	dropoff_location_dim.to_sql('dropoff_location_dim', engine)
	payment_type_dim.to_sql('payment_type_dim', engine)
	fact_table.to_sql('fact_table', engine)

	
	# conn = psycopg2.connect(
	# dbname = "modeling_uber_data",
	# user = "airflow",
	# password = "airflow",
	# host = "postgres",
	# port = 5432
	# )

	# cursor = conn.cursor()
	# sql = """SELECT * FROM modeling_uber_data.pg_tables;"""
	# cursor.execute(sql)
	# for i in cursor.fetchall():
	# 	print(i)
	# conn.close()

with DAG(
    'etl_uber_data',
    default_args=default_args,
    description='ETL Uber Data',
    schedule_interval=timedelta(days=1),
) as dag:
	extract_data = PythonOperator(
		task_id='extract',
		python_callable=extract
    )
	transform_data = PythonOperator(
		task_id='transform',
		python_callable=transform,
    )
	load_data = PythonOperator(
		task_id='load_postgres',
		python_callable=load
	)
		
# task pipeline
extract_data >> transform_data >> load_data