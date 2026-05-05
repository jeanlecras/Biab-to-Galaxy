import json
import duckdb
import base64
import requests
import sys
import os

print("initialising duckdb")
ddb = duckdb.connect()
ddb.install_extension("spatial")
ddb.load_extension("spatial")
ddb.install_extension("httpfs")
ddb.load_extension("httpfs")

countries_parquet = "https://data.fieldmaps.io/adm0/osm/intl/adm0_polygons.parquet"
regions_parquet = "https://data.fieldmaps.io/edge-matched/humanitarian/intl/adm1_polygons.parquet"


CRS_NAME2CODE = {
    "WGS 84 / Latitude-Longitude": 4326,
    "WGS 84 / Pseudo-Mercator": 3857,
    "WGS 84 / Equal Earth Greenwich": 8857
}
    

key = base64.b64decode("VTRoTkxXUkVOeFRhN0NmSFVVbk4=").decode("utf-8")

def get_crs_def(epsg_number):
    base_url = f"https://api.maptiler.com/coordinates/search/{epsg_number}.json"
    params = {
        "limit": 2,
        "exports": True,
        "key": key,
    }

    try:
        print("requesting", base_url)
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if (
            results
            and results[0].get("exports")
            and results[0]["exports"].get("proj4")
        ):
            return results[0]
        else:
            raise ValueError(f"CRS definition not found for {epsg_number}")

    except Exception as e:
        print(f"get_crs_def error: {e}")
        return None

def generate_input_file(args):
    input_data = {}
    
    for i in range(1, len(args), 3):
        print("args", args)
        param_name, param_type, param_value = args[i:i+3]
        
        input_data[param_name] = {
            "country": None,
            "region": None,
            "bbox": [],
            "CRS": { # default CRS when no CRS is selected
                "name": "WGS84 - Lat/long",
                "authority": "EPSG",
                "code": 4326,
                "proj4Def": "+proj=longlat +datum=WGS84 +no_defs",
                "unit": "degree",
                }
            }
            
        match param_type:
            case "boolean":
                input_data[param_name] = param_value=="true"
                
            case "int":
                input_data[param_name] = int(param_value)
                
            case "float":
                input_data[param_name] = float(param_value)
                
            case "options[]":
                input_data[param_name] = param_value.split(",")
                
            case "text[]":
                input_data[param_name] = param_value.split(",")
                
            case "int[]":
                input_data[param_name] = list(map(int, param_value.split(",")))
                
            case "float[]":
                input_data[param_name] = list(map(float, param_value.split(",")))
            
            case "country":
                country_query = f"""
                select adm0_name, geometry_bbox
                from read_parquet('{countries_parquet}')
                where adm0_src = '{param_value}'
                """
                country_data = ddb.execute(country_query).fetchone()
                input_data[param_name]["country"] = {
                    "englishName": country_data[0],
                    "code": param_value[:2],
                    "ISO3": param_value,
                    "countryBboxWGS84": list(country_data[1].values())
                    }
                
            case "region":
                if param_value != 'None':
                    region_query = f"""
                    select adm0_src, adm1_name, geometry_bbox
                    from read_parquet('{regions_parquet}')
                    where adm1_src = '{param_value}'
                    """
                    region_data = ddb.execute(region_query).fetchone()
                    input_data[param_name]["region"] = {
                        "ISO3166_2": region_data[0],
                        "countryEnglishName": input_data[param_name]["country"]["englishName"],
                        "regionName": region_data[1],
                        "regionBboxWGS84": list(region_data[2].values())
                        }
            
            case "xmin" | "ymin" | "xmax" | "ymax":
                input_data[param_name]["bbox"].append(param_value)
                
            case "crs":
                authority, code = param_value.split(":")
                crs_data = get_crs_def(code)
                input_data[param_name]["CRS"]["authority"] = authority
                input_data[param_name]["CRS"]["code"] = code
                input_data[param_name] = {
                    "authority": authority,
                    "code": code,
                    "name": crs_data['name'],
                    "unit": crs_data['unit'],
                    "CRSBboxWGS84": crs_data['bbox'],
                    "proj4Def": crs_data['proj4Def'],
                    "wktDef": crs_data['wktDef']
                    }
            
            case _: # including types text, options and mime
                if not param_type.endswith("[]"):
                    input_data[param_name] = param_value
                else:
                    collection = param_value.split(",")
                    collection.pop()
                    collection_path = os.path.abspath(param_name)
                    input_data[param_name] = [collection_path+"/"+element for element in collection]
                    
                
    with open("input.json", "w") as f:
        json.dump(input_data, f)


if __name__ == "__main__":
    print(sys.argv)
    generate_input_file(sys.argv)
