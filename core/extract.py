import os
import polars as pl
from sodapy import Socrata
from datetime import datetime, timedelta

class CTACrime:
    base_url = "data.cityofchicago.org"
    crimes = "ijzp-q8t2"
    rail_stations = "3tzw-cg4m"
    rail_lines = "xbyr-jnvx"
    
    def __init__(self, 
                 api_key_id: str = os.environ["socrata_username"],
                 api_key_secret: str = os.environ["socrata_password"],
                 token: str = os.environ["socrata_app_token"]):
        self.client = Socrata(
            CTACrime.base_url,
            app_token = token,
            username = api_key_id,
            password = api_key_secret
            )

    def get_schema(self, as_table: bool = False) -> dict | pl.DataFrame:
        '''
        as_table: Whether or not to return the schema as a Polars table. Defaults to False.
        
        Returns the schema of the Chicago crimes table.
        '''
        schema = {}
        response = self.client.get_metadata(CTACrime.crimes)
        
        for column in response["columns"]:
            schema[column["name"]] = column.get("description", "")
        
        if not as_table:
            return schema
        else:
            return pl.DataFrame(
                data = list(schema.items()), 
                schema = ["column", "description"]
                )

    def _all_columns(self) -> set:
        return set(self.get_schema().keys())
    
    @staticmethod
    def _cta_locations():
        return [
            'CTA "L" PLATFORM',
            'CTA "L" TRAIN',
            'CTA PLATFORM',
            'CTA SUBWAY STATION',
            'CTA TRACKS - RIGHT OF WAY',
            'CTA TRAIN',
        ]
    
    def run_query(self, query: str) -> dict:
        return self.client.get(CTACrime.crimes, query = query)
    
    def test_query(self, num_rows: int = 5) -> pl.DataFrame:
        response = self.run_query(query = f"SELECT * LIMIT {num_rows}")
        
        return pl.DataFrame(response)
    
    def get_max_date(self, date_column: str = "Date") -> str:
        if date_column not in self._all_columns():
            raise Exception(f"Date column '{date_column}' not found. Do get_schema() for to get all columns.")
        
        response = self.run_query(query = f"SELECT MAX({date_column}) AS max_date")
        
        return response[0]["max_date"]

    def get_unique_values(self, column: str) -> dict:
        if column not in self._all_columns():
            raise Exception(f"Column '{column}' not found. Do get_schema() for to get all columns.")
        
        return self.run_query(query = f"SELECT DISTINCT {column}")
    
    def get_cta_crimes(self, last_n_days: int = 30) -> pl.DataFrame:
        max_date = self.get_max_date()
        
        start_date = (datetime.fromisoformat(max_date) - timedelta(days = last_n_days - 1)).isoformat()
        
        cta_locations = ", ".join(f"'{loc}'" for loc in CTACrime._cta_locations())
        
        query = f"""
        SELECT case_number, date, primary_type, location_description, longitude, latitude
        WHERE date >= '{start_date}' AND location_description IN ({cta_locations})
        """
        
        response = self.run_query(query = query)
        
        return pl.DataFrame(response)
    
    def cta_rail_stations(self) -> pl.DataFrame:
        response = self.client.get(CTACrime.rail_stations)
        
        return pl.DataFrame(response)
    
    def cta_rail_lines(self) -> pl.DataFrame:
        response = self.client.get(CTACrime.rail_lines)
        
        return pl.DataFrame(response)
