# au lieu de faire des choses actions particulières pour chaque biab type différent, gérer un seul cas : bboxCRS car tous les autres paramètres sont inclus dans celui ci.
# cette fonction renverra un fichier input contenant un bboxCRS complet ou incomplet
# tous les commandes de type spécial utiliseront les mêmes paramètres dans le même ordre mais pas complété de la même manière
# ordre : country, region, xmin, ymin, xmax, ymax, crs_name, crs_code length=8
# les scripts biab retrouvet les valeurs de leurs varibales avec le nom du paramètre comme clé du dictionnaire input
# les arguments peuvent être nommés par le nom de leur paramètre
# si tous les types spéciaux sont considérés comme une forme de bboxCRS alors il n'y a pas besoin de rensiegner le type spécial, juste le nom du paramètre et le sous paramètre
# il ne faut pas passer sys.argv en brute à la fonction, il faut un dictionnaire qui représente un paramètre par un nom et une valeur
# SI mais il faut que la fonction ait un parseur

import json
import duckdb

#GENERATING countries.tsv AND regions.tsv
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

def parser(args):
    parsed_args = {}
    for i in range(len(args)//2):
        if not args[2*i].startswith("--"):
            continue
        arg_name = args[2*i][2:]
        parsed_args[arg_name] = args[2*i+1]
    return parsed_args

def generate_input_file(args):
    parsed_args = parser(args)
    input_data = {}
    for arg_name, arg_value in parsed_args.items():
        if '__' not in arg_name:
            input_data[arg_name] = arg_value
            continue
        
        param, sub_param = arg_name.split('__')
        if param not in input_data:
            input_data[param] = {
                "country": {},
                "region": {},
                "bbox": [],
                "CRS": {}
                }
            
        match sub_param:
            case "country":
                # requête sql qui récupère adm0_src, geometry_bbox o`u adm0_name == country
                country_query = f"""
                select adm0_name, geometry_bbox
                from read_parquet('{countries_parquet}')
                where adm0_src = '{arg_value}'
                """
                country_data = ddb.execute(country_query).fetchone()
                input_data[param]["country"] = {
                    "englishName": country_data[0],
                    "code": arg_value[:2],
                    "ISO3": arg_value,
                    "countryBboxWGS84": list(country_data[1].values())
                    }
                
            case "region":
                if arg_value != 'None':
                    # requête sql qui récupère adm0_src, geometry_bboc o`u adm1_name == region
                    region_query = f"""
                    select adm0_src, adm1_name, geometry_bbox
                    from read_parquet('{regions_parquet}')
                    where adm1_src = '{arg_value}'
                    """
                    region_data = ddb.execute(region_query).fetchone()
                    input_data[param]["region"] = {
                        "ISO3166_2": region_data[0],
                        "countryEnglishName": input_data[param]["country"]["englishName"],
                        "regionName": region_data[1],
                        "regionsBboxWGS84": list(region_data[2].values())
                        }
                
            case "xmin" | "ymin" | "xmax" | "ymax":
                input_data[param]["bbox"].append(arg_value)
                
            case "crs_name":
                # TODO trouver l'origine de ces trucs
                input_data[param]["CRS"] = {
                    "name": arg_value,
                    "authority": "EPSG",
                    "code": CRS_NAME2CODE[arg_value],
                    # c'est la plaie, je remets à plus tard
                    "unit": None,
                    "proj4Def": None,
                    "wktDef": None,
                    # pourquoi un CRS doit avoir une bbox ?
                    "CRSBboxWGS84": None
                    }
                
            case "crs_code":
                authority, code = arg_value.split(":")
                input_data[param]["CRS"] = {
                    "name": None,
                    "authority": authority,
                    "code": code,
                    "CRSBboxWGS84": None,
                    "proj4Def": None,
                    "wktDef": None
                    }
                
    with open("input.json", "w") as f:
        json.dump(input_data, f)