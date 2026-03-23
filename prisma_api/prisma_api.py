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

        response = requests.post(url, json=payload, headers=headers, timeout=60)
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
            response = requests.post(url, json=payload, headers=headers, timeout=60)
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
    
    def get_carbon_data_nested(self, payload={}, safe_names=False):
        """
        Get carbon data with nested structure, returned as separate DataFrames.

        Args:
            payload:    Dictionary containing query parameters for filtering
            safe_names: If True (default), keep API-safe column names (e.g. 'Pressure_bar').
                        If False, rename columns to original names (e.g. 'Pressure [bar]').

        Returns:
            dict: {
                'Simulated':    {'isotherm': pd.DataFrame, 'geometry': pd.DataFrame},
                'Experimental': {'isotherm': pd.DataFrame, 'geometry': pd.DataFrame},
                'meta':         dict
            }
        """
        api = self

        if self.dev:
            url = f"http://localhost:{self.dev_host_port}/api/get_carbon_data_nested/"
        else:
            url = "https://www.dun-eideann-labs.co.uk/prisma_cloud/api/get_carbon_data_nested/"

        headers = {
            "X-API-Key": api.key,
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            data = response.json()

            col_names_carbon = data.get('meta', {}).get('original_column_names', {})
            col_names_water = data.get('meta', {}).get('Water', {}).get('original_column_names', {})

            # col_names maps: api_field_name -> original_column_name
            # Use directly as a rename map for each DataFrame
            sim_iso   = pd.DataFrame(data.get('Simulated',    {}).get('isotherm',  []))
            sim_geo   = pd.DataFrame(data.get('Simulated',    {}).get('geometry',  []))
            exp_iso   = pd.DataFrame(data.get('Experimental', {}).get('isotherm',  []))
            exp_geo   = pd.DataFrame(data.get('Experimental', {}).get('geometry',  []))

            sim_water_dac = pd.DataFrame(data.get('Water', {}).get('Simulated',    {}).get('DAC',  []))
            sim_water_cement = pd.DataFrame(data.get('Water', {}).get('Simulated',    {}).get('cement',  []))
            sim_water_coal = pd.DataFrame(data.get('Water', {}).get('Simulated',    {}).get('coal',  []))
            sim_water_ngcc = pd.DataFrame(data.get('Water', {}).get('Simulated',    {}).get('NGCC-onshore',  []))
            exp_water_dac = pd.DataFrame(data.get('Water', {}).get('Experimental', {}).get('DAC',  []))
            exp_water_cement = pd.DataFrame(data.get('Water', {}).get('Experimental', {}).get('cement',  []))
            exp_water_coal = pd.DataFrame(data.get('Water', {}).get('Experimental', {}).get('coal',  []))
            exp_water_ngcc = pd.DataFrame(data.get('Water', {}).get('Experimental', {}).get('NGCC-onshore',  []))

            if not safe_names:
                if col_names_carbon.get('isotherm'):
                    sim_iso = sim_iso.rename(columns=col_names_carbon['isotherm'])
                    exp_iso = exp_iso.rename(columns=col_names_carbon['isotherm'])

                if col_names_carbon.get('simulated_geometry'):
                    sim_geo = sim_geo.rename(columns=col_names_carbon['simulated_geometry'])

                if col_names_carbon.get('experimental_geometry'):
                    exp_geo = exp_geo.rename(columns=col_names_carbon['experimental_geometry'])

                if col_names_water:
                    sim_water_dac = sim_water_dac.rename(columns=col_names_water)
                    exp_water_dac = exp_water_dac.rename(columns=col_names_water)
                    sim_water_cement = sim_water_cement.rename(columns=col_names_water)
                    exp_water_cement = exp_water_cement.rename(columns=col_names_water)
                    sim_water_coal = sim_water_coal.rename(columns=col_names_water)
                    exp_water_coal = exp_water_coal.rename(columns=col_names_water)
                    sim_water_ngcc = sim_water_ngcc.rename(columns=col_names_water)
                    exp_water_ngcc = exp_water_ngcc.rename(columns=col_names_water)

            return {
                'Simulated': {'isotherm':    sim_iso, 'geometry': sim_geo},
                'Experimental': {'isotherm': exp_iso, 'geometry': exp_geo},
                'meta':                  data.get('meta', {}),
                'Water': {
                    'Simulated': {'DAC':    sim_water_dac, 'cement': sim_water_cement, 'coal': sim_water_coal, 'NGCC-onshore': sim_water_ngcc},
                    'Experimental': {'DAC': exp_water_dac, 'cement': exp_water_cement, 'coal': exp_water_coal, 'NGCC-onshore': exp_water_ngcc},
                    'meta':                  data.get('meta', {}).get('water', {}),
                }
            }

        except Exception as e:
            print(f"Error retrieving carbon data nested: {e}")
            return {}
    
    def get_materials_data(self, payload={}, unpack_nested=True):
        """
        """
        api = self

        if self.dev:
            url = f"http://localhost:{self.dev_host_port}/api/get_materials_data/"
        else:
            url = "https://www.dun-eideann-labs.co.uk/prisma_cloud/api/get_materials_data/"

        headers = {
            "X-API-Key": api.key,
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            data_raw = response.json()
            
            df = pd.DataFrame(data_raw.get('data', []))

            if unpack_nested and not df.empty:
                # Unpack carbon_isotherm independently (keep prefixed columns)
                if 'carbon_isotherm' in df.columns:
                    unpacked = pd.json_normalize(
                        df['carbon_isotherm'].apply(lambda x: x[0] if isinstance(x, list) and len(x) > 0 else (x if isinstance(x, dict) else {}))
                    )
                    unpacked.columns = [f"carbon_isotherm__{c}" for c in unpacked.columns]
                    df = df.drop(columns=['carbon_isotherm']).join(unpacked)

                # Unpack carbon_zeopp and carbon_zeopp_experimental, then combine shared fields
                zeopp_cols = [c for c in ['carbon_zeopp', 'carbon_zeopp_experimental'] if c in df.columns]
                if zeopp_cols:
                    unpacked_frames = {}
                    for col in zeopp_cols:
                        unpacked = pd.json_normalize(
                            df[col].apply(lambda x: x[0] if isinstance(x, list) and len(x) > 0 else (x if isinstance(x, dict) else {}))
                        )
                        unpacked_frames[col] = unpacked
                        df = df.drop(columns=[col])

                    # Derive sim_or_exp flag: 'exp' if carbon_zeopp_experimental has data, else 'sim'
                    if 'carbon_zeopp_experimental' in unpacked_frames:
                        exp_has_data = unpacked_frames['carbon_zeopp_experimental'].notna().any(axis=1)
                    else:
                        exp_has_data = pd.Series(False, index=df.index)

                    zeopp_sim_or_exp = exp_has_data.map({True: 'exp', False: 'sim'})

                    # Collect all field names across both unpacked frames
                    all_fields = set()
                    for unpacked in unpacked_frames.values():
                        all_fields.update(unpacked.columns)
                    all_fields.discard('sim_or_exp')

                    # Coalesce: for shared fields prefer carbon_zeopp, fall back to carbon_zeopp_experimental
                    combined = pd.DataFrame(index=df.index)
                    for field in sorted(all_fields):
                        series_list = [unpacked_frames[col][field] for col in zeopp_cols if field in unpacked_frames[col].columns]
                        if len(series_list) == 1:
                            combined[f"carbon_zeopp__{field}"] = series_list[0].values
                        else:
                            coalesced = series_list[0].copy()
                            for fallback in series_list[1:]:
                                coalesced = coalesced.combine_first(fallback.rename(coalesced.name))
                            combined[f"carbon_zeopp__{field}"] = coalesced.values

                    df = df.join(combined)

                # Build a single top-level sim_or_exp column, coalescing sources in priority order
                sim_or_exp = pd.Series(index=df.index, dtype=object)
                for source_col in ['carbon_isotherm__sim_or_exp', 'carbon_zeopp__sim_or_exp']:
                    if source_col in df.columns:
                        sim_or_exp = sim_or_exp.combine_first(df[source_col])
                        df = df.drop(columns=[source_col])
                # Fall back to the zeopp-derived flag if still null
                if 'zeopp_sim_or_exp' in locals():
                    sim_or_exp = sim_or_exp.combine_first(zeopp_sim_or_exp)

                # Insert sim_or_exp as the first column after unpacking
                df.insert(0, 'sim_or_exp', sim_or_exp)

            data = {
                'simulated': df,
                'experimental': df,
            }
            
            return data

        except Exception as e:
            print(f"Error retrieving materials data: {e}")
            return {}
    
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