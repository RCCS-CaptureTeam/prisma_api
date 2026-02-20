from .config import get_or_create_config, update_dev_mode as _update_dev_mode
from pathlib import Path
import pandas as pd
import requests

import numpy as np
import json
import math

def _safe_nan_check(x):
    if x is None:
        return None
    try:
        if isinstance(x, (int, float)) and math.isnan(x):
            return None
    except (TypeError, ValueError):
        pass
    return x

  

# prisma_api main class
class prisma_api():

    def __init__(self):
        
        # Initialise `prisma_api` object with api_key location
        self.verbose = False
        # Initialise `prisma_api` object with api_key location
        cfg = get_or_create_config()
        self.key = cfg['api_key']
        self.dev = cfg.get('dev', False)
        if self.dev:
            self.dev_host_port = cfg['dev_host_port']
            self.key = cfg['dev_api_key']
    
    def update_dev_mode(self, dev: bool):
        """Update the dev flag in config.yaml.
        
        Args:
            dev: Boolean flag to enable/disable dev mode.
            
        Returns:
            dict: Updated config.
        """
        return _update_dev_mode(dev)
        
    def get_mofs(self, payload={}):

        api = self

        if self.dev:
            url = f"http://localhost:{self.dev_host_port}/api/get_mofs/"
        else:
            url = "https://www.dun-eideann-labs.co.uk/prisma_cloud/api/get_mofs/"

        headers = {
            "X-API-Key": api.key,
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=payload, headers=headers)
        data = response.json()['data']

        data = pd.DataFrame.from_dict(data)

        return data
    
    
    def get_carbon_isotherms(self, payload={}):

        api = self

        if self.dev:
            url = f"http://localhost:{self.dev_host_port}/api/get_carbon_isotherms/"
        else:
            url = "https://www.dun-eideann-labs.co.uk/prisma_cloud/api/get_carbon_isotherms/"

        headers = {
            "X-API-Key": api.key,
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            data = response.json()['data']

            data = pd.DataFrame.from_dict(data)
            
            # Flatten nested mof fields
            if 'mof' in data.columns and not data.empty:
                mof_df = pd.json_normalize(data['mof'])
                mof_df.columns = ['mof_' + col for col in mof_df.columns]
                data = pd.concat([data.drop('mof', axis=1), mof_df], axis=1)
            
            # Flatten nested molecule fields
            if 'molecule' in data.columns and not data.empty:
                molecule_df = pd.json_normalize(data['molecule'])
                molecule_df.columns = ['molecule_' + col for col in molecule_df.columns]
                data = pd.concat([data.drop('molecule', axis=1), molecule_df], axis=1)

            return data
        
        except Exception as e:
            print("Error retrieving carbon isotherms: check that the query parameter names are correct.")
            return pd.DataFrame()
        
    #### --------------------------  AutoPrism  -------------------------- ####

    def update_adsorption_singlepoint(self, df):
        """
        Update adsorption singlepoint data via PUT request.
        
        Args:
            df: DataFrame containing the adsorption singlepoint data to update
            
        Returns:
            pd.DataFrame: Response data from the API
        """
        api = self

        if self.dev:
            url = f"http://localhost:{self.dev_host_port}/api/update_adsorption_singlepoint/"
        else:
            url = "https://www.dun-eideann-labs.co.uk/prisma_cloud/api/update_adsorption_singlepoint/"

        headers = {
            "X-API-Key": api.key,
            "Content-Type": "application/json"
        }

        # Convert dataframe to JSON payload, handling NaN and infinite values
        json_data = self._clean_dataframe_for_json(df)

        response = requests.put(url, data=json_data, headers=headers, timeout=300) # 300sec (5 minutes)
        
        return response.json()

    def _clean_dataframe_for_json(self, df):
        """Helper method to clean DataFrame for JSON serialization."""
        if df.empty:
            return "[]"
        
        import numpy as np
        import json
        
        # Use pandas to_json which handles NaN properly, then parse back
        df_clean = df.copy()
        df_clean = df_clean.replace([np.nan, np.inf, -np.inf], None)
        
        # Convert using pandas to_json (which handles NaN correctly) then back to dict
        json_str = df_clean.to_json(orient='records', force_ascii=False)
        
        return json_str

    def update_heat_capacity_all_tidy(self, df):
        """
        Update heat capacity all tidy data via PUT request.
        
        Args:
            df: DataFrame containing the heat capacity data to update
            
        Returns:
            dict: Response data from the API
        """
        if self.dev:
            url = f"http://localhost:{self.dev_host_port}/api/update_heat_capacity_all_tidy/"
        else:
            url = "https://www.dun-eideann-labs.co.uk/prisma_cloud/api/update_heat_capacity_all_tidy/"

        headers = {
            "X-API-Key": self.key,
            "Content-Type": "application/json"
        }

        json_data = self._clean_dataframe_for_json(df)
        response = requests.put(url, data=json_data, headers=headers, timeout=300)
        
        return response.json()

    def update_isotherm_h2(self, df):
        """
        Update H2 isotherm data via PUT request.
        
        Args:
            df: DataFrame containing the H2 isotherm data to update
            
        Returns:
            dict: Response data from the API
        """
        if self.dev:
            url = f"http://localhost:{self.dev_host_port}/api/update_isotherm_h2/"
        else:
            url = "https://www.dun-eideann-labs.co.uk/prisma_cloud/api/update_isotherm_h2/"

        headers = {
            "X-API-Key": self.key,
            "Content-Type": "application/json"
        }

        json_data = self._clean_dataframe_for_json(df)
        response = requests.put(url, data=json_data, headers=headers, timeout=300)
        
        return response.json()

    def update_mofchecker(self, df):
        """
        Update MOF checker data via PUT request.
        
        Args:
            df: DataFrame containing the MOF checker data to update
            
        Returns:
            dict: Response data from the API
        """
        if self.dev:
            url = f"http://localhost:{self.dev_host_port}/api/update_mofchecker/"
        else:
            url = "https://www.dun-eideann-labs.co.uk/prisma_cloud/api/update_mofchecker/"

        headers = {
            "X-API-Key": self.key,
            "Content-Type": "application/json"
        }

        json_data = self._clean_dataframe_for_json(df)
        response = requests.put(url, data=json_data, headers=headers, timeout=300)
        
        return response.json()

    def update_zeopp_metrics(self, df):
        """
        Update Zeo++ metrics data via PUT request.
        
        Args:
            df: DataFrame containing the Zeo++ metrics data to update
            
        Returns:
            dict: Response data from the API
        """
        if self.dev:
            url = f"http://localhost:{self.dev_host_port}/api/update_zeopp_metrics/"
        else:
            url = "https://www.dun-eideann-labs.co.uk/prisma_cloud/api/update_zeopp_metrics/"

        headers = {
            "X-API-Key": self.key,
            "Content-Type": "application/json"
        }

        json_data = self._clean_dataframe_for_json(df)
        response = requests.put(url, data=json_data, headers=headers, timeout=300)
        
        return response.json()