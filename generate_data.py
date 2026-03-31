import duckdb
from pathlib import Path
import xml.etree.ElementTree as ET
from argparse import ArgumentParser

def parse_args():
    parser = ArgumentParser(
        description="Generates the data tables files required to use a bon in a box tool.\
            These tools often have a country and region parameter, these parameters are listss whose values come from the generated data tables\
            These tool also declares the data tables in to the tool_data_table_conf.xml.sample file"
        )
        
    parser.add_argument("galaxy_path", help="Path of the galaxy instance repository")
    args = parser.parse_args()
    galaxy_path = args.galaxy_path
    
    countries_path = Path(galaxy_path) / "tool-data" / "countries.loc"
    regions_path = Path(galaxy_path) / "tool-data" / "regions.loc"
    tool_data_conf_path = Path(galaxy_path) / "config" / "tool_data_table_conf.xml.sample"
    return countries_path, regions_path, tool_data_conf_path

###################
# GENERATING DATA #
###################
def generate_data(countries_path, regions_path):
    ddb = duckdb.connect()
    ddb.install_extension("spatial")
    ddb.load_extension("spatial")
    ddb.install_extension("httpfs")
    ddb.load_extension("httpfs")

    countries_parquet = "https://data.fieldmaps.io/adm0/osm/intl/adm0_polygons.parquet"
    regions_parquet = "https://data.fieldmaps.io/edge-matched/humanitarian/intl/adm1_polygons.parquet"
    
    print("querying data...")
    countries=ddb.sql("""
                      SELECT 
                          adm0_src as value, 
                          adm0_name as name
                      FROM read_parquet('%s')
                      """ % countries_parquet).df()
    countries.to_csv(countries_path, sep='\t', index=False)
    
    regions=ddb.sql("""
                    SELECT 
                        adm1_src as value, 
                        adm1_name as name
                    FROM read_parquet('%s')
                    """ % regions_parquet).df()
    regions.to_csv(regions_path, sep='\t', index=False)
    
    print("data successfully retrieved")
    
    with open(countries_path, "r") as f:
        header = f.readline()
        data = f.read()
    
    with open(countries_path, "w") as f:
        f.write("# " + header + data)
        
    
    with open(regions_path, "r") as f:
        header = f.readline()
        data = f.read()
    
    with open(regions_path, "w") as f:
        f.write("# " + header + data)
    

#############################
# DECLARING FILES IN CONFIG #
#############################

def declare_tables(tool_data_conf_path):
    print("declaring data tables to tool_data_table_conf.xml...")
    tree = ET.parse(tool_data_conf_path)
    root = tree.getroot()
    
    existing = {t.get("name") for t in root.findall("table")}
    
    # Definition of tables to add if missing
    missing_tables = []
    
    if "regions" not in existing:
        regions = ET.fromstring(
            '<table name="regions" comment_char="#" allow_duplicate_entries="False">\n'
            '        <columns>value, name, adm0_src, adm0_name, geometry_bbox</columns>\n'
            '        <file path="tool-data/regions.loc" />\n'
            '    </table>'
        )
        missing_tables.append(("regions", regions))
    
    if "countries" not in existing:
        countries = ET.fromstring(
            '<table name="countries" comment_char="#" allow_duplicate_entries="False">\n'
            '        <columns>value, name, geometry_bbox</columns>\n'
            '        <file path="tool-data/countries.loc" />\n'
            '    </table>'
        )
        missing_tables.append(("countries", countries))
    
    if not missing_tables:
        print("The data tables'regions' and 'countries' already exist. No modification.")
    else:
        for name, element in missing_tables:
            root.append(element)
            print(f"Data table '{name}' added.")
    
    ET.indent(tree, space="    ")
    tree.write(tool_data_conf_path, encoding="unicode", xml_declaration=True)
    print(f"File saved : {tool_data_conf_path}")

if __name__ == "__main__":
    countries_path, regions_path, tool_data_conf_path = parse_args()
    generate_data(countries_path, regions_path)
    declare_tables(tool_data_conf_path)