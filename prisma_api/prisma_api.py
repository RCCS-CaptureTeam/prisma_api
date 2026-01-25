from .config import get_or_create_config, update_dev_mode as _update_dev_mode
from pathlib import Path
import pandas as pd
import requests
  

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
            url = "https://www.dun-eideann-labs.co.uk/prisma_db/api/get_mofs/"

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
            url = "https://www.dun-eideann-labs.co.uk/prisma_db/api/get_carbon_isotherms/"

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