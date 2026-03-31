# Bon in a box to Galaxy tool converter

[Bon in a box](https://boninabox.geobon.org/) and [Galaxy](https://usegalaxy.org/) are two platforms for building and sharing scientific workflows. This tool helps developers migrate Biab tools to Galaxy by automating part of the process.

## Features
- Generation of Galaxy wrapper file based on Biab wrapper file
    - Generation of a Cheetah command
    - Generation of input parameters
    - Generation of output data and collecions
    - Managing requirements
- Creation of modified Biab script adapted to Galaxy
    - Rewriting Biab dependant functions
    - Deadling with Biab special types (bbox, CRS, country, region...)
    - Detecting credentials variables
- Adding a converted tool to the Galaxy's list of tools
- Generation of a .shed.yml file

## requirements

- local Galaxy instance (highly recommended)
- python 3.12+
- duckdb
- PyYAML

Instal dependencies:
```
pip install duckdb pyyaml
```

## Usage

**Arguments**:
- yml file for the Biab tool wrapper
- R/python/julia file for the Biab tool script
- xml file for Galaxy tool wrapper to be created
- R/python/julia file for the Galaxy tool script to be created
- `-g` : path to the local Galaxy instance (optional)

### 1. Convert a tool
Creates a Galaxy wrapper.xml file based on the Biab wrapper.yml file.
Creates a Galaxy script file based on the biab script file.

```
python biab_to_galaxy.py biab_wrapper biab_script galaxy_wrapper galaxy_script
```

### 2. Port a tool into galaxy

Converts a tool. Add the tool to the galaxy tool list. Creates a .shed.yml file and generates the necessary data tables if they don't exist yet.

```
python biab_to_galaxy.py biab_wrapper biab_script galaxy_wrapper galaxy_script -g galaxy_repository
```

## What this converter can't do
- Generate tests for the converted tools
- Generate an appropriate tool description
- Differentiate optional and required parameters
- Find extension(s) for any Biab (MIME) type

## Missing features
- Handling of data_collection in outputs
- Validator to check if the bounding box coordinates are valid (ex: xmin < xmax, ymin < ymax)
- Julia scripts support
- Fixed versions for default R dependencies
- Fixed versions given to dependencies with no specified version
- Robust R parser (the current one is based on regex)
- Exhaustive mapping of file extensions to MIME types
