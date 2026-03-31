import re
import os


# ──────────────────────────────────────────────────────────────────────────────
# 1. Replace biab_* functions
# ──────────────────────────────────────────────────────────────────────────────

def replace_biab_functions(script_path):
    """
    Replaces biab_* function calls and accumulation patterns
    (error <- c(error, ...), warning <- c(warning, ...), info <- c(info, ...))
    with their standard R equivalents.

    Transformations:
      biab_error_stop(message)          → stop(message)
      biab_warning(message)             → warning(message)
      biab_info(message)                → message(message)
      error <- c(error, message)        → stop(message)
      warning <- c(warning, message)    → warning(message)
      info <- c(info, message)          → message(message)
    """
    with open(script_path, 'r', encoding='utf-8') as f:
        source_code = f.read()

    # biab_error_stop(...) → stop(...)
    source_code = re.sub(
        r'\bbiab_error_stop\s*\(', 'stop(', source_code
    )

    # biab_warning(...) → warning(...)
    source_code = re.sub(
        r'\bbiab_warning\s*\(', 'warning(', source_code
    )

    # biab_info(...) → message(...)
    source_code = re.sub(
        r'\bbiab_info\s*\(', 'message(', source_code
    )

    # error <- c(error, msg)  → stop(msg)
    source_code = re.sub(
        r'\berror\s*<-\s*c\s*\(\s*error\s*,\s*(.*?)\)',
        lambda m: f'stop({m.group(1)})',
        source_code
    )

    # warning <- c(warning, msg)  → warning(msg)
    source_code = re.sub(
        r'\bwarning\s*<-\s*c\s*\(\s*warning\s*,\s*(.*?)\)',
        lambda m: f'warning({m.group(1)})',
        source_code
    )

    # info <- c(info, msg)  → message(msg)
    source_code = re.sub(
        r'\binfo\s*<-\s*c\s*\(\s*info\s*,\s*(.*?)\)',
        lambda m: f'message({m.group(1)})',
        source_code
    )

    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(source_code)


# ──────────────────────────────────────────────────────────────────────────────
# 2. Inputs handling  (biab_inputs() → read input.json via jsonlite)
# ──────────────────────────────────────────────────────────────────────────────

def add_inputs_handling(script_path):
    """
    - Replaces  var <- biab_inputs()  with a read from input.json
      (the file must already exist before the script is executed).
    - Prepends output_folder <- getwd() to the script.
    """
    with open(script_path, 'r', encoding='utf-8') as f:
        source_code = f.read()

    # var <- biab_inputs()
    #   →  var <- jsonlite::read_json("input.json", simplifyVector = TRUE)
    source_code = re.sub(
        r'(\w+)\s*<-\s*biab_inputs\s*\(\s*\)',
        r'\1 <- jsonlite::read_json("input.json", simplifyVector = TRUE)',
        source_code
    )

    header = 'output_folder <- getwd()\n\n'
    source_code = header + source_code

    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(source_code)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Outputs handling  (biab_output() → file.rename())
# ──────────────────────────────────────────────────────────────────────────────

def add_outputs_handling(script_path, replacements):
    """
    Replaces  biab_output("name", src_path)  calls with
        file.rename(src_path, "new_path")
    for outputs present in `replacements`.

    Outputs not found in the script are handled via output.json at the end.

    Args:
        script_path  : path to the R script to modify
        replacements : dict { output_name: new_file_path }

    Raises:
        ValueError if an output_name is found neither in the script nor in output.json
    """
    with open(script_path, 'r', encoding='utf-8') as f:
        source_code = f.read()

    found_in_script = set()

    def _replace_output(m):
        output_name = m.group(1).strip().strip('"\'')
        src_expr    = m.group(2).strip()
        if output_name in replacements:
            found_in_script.add(output_name)
            new_path = replacements[output_name]
            return f'file.rename({src_expr}, "{new_path}")'
        return m.group(0)   # not in replacements → leave as-is

    # biab_output("name", expr)  — both arguments may be separated
    # by spaces or newlines
    source_code = re.sub(
        r'biab_output\s*\(\s*(["\'][^"\']+["\'])\s*,\s*([^)]+)\)',
        _replace_output,
        source_code
    )

    expected_in_json = set(replacements.keys()) - found_in_script

    if expected_in_json:
        outputs_mapping = {n: replacements[n] for n in sorted(expected_in_json)}
        expected_vec    = ', '.join(f'"{n}"' for n in sorted(expected_in_json))

        # Generate the R block that reads output.json
        mapping_items = ', '.join(f'{k} = "{v}"' for k, v in outputs_mapping.items())
        lines = [
            '',
            '# --- Outputs handling via output.json ---',
            'library(jsonlite)',
            f'outputs_mapping <- list({mapping_items})',
            'output_json_path <- file.path(output_folder, "output.json")',
            'if (file.exists(output_json_path)) {',
            '  outputs_from_json <- jsonlite::read_json(output_json_path, simplifyVector = TRUE)',
            f'  expected_outputs  <- c({expected_vec})',
            '  missing_outputs   <- setdiff(expected_outputs, names(outputs_from_json))',
            '  if (length(missing_outputs) > 0) {',
            '    stop(paste("The following output_names were not found in output.json:",',
            '               paste(missing_outputs, collapse = ", ")))',
            '  }',
            '  for (output_name in names(outputs_mapping)) {',
            '    if (output_name %in% names(outputs_from_json)) {',
            '      file.rename(outputs_from_json[[output_name]], outputs_mapping[[output_name]])',
            '    }',
            '  }',
            '}',
        ]
        source_code = source_code.rstrip('\n') + '\n' + '\n'.join(lines) + '\n'

    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(source_code)


# ──────────────────────────────────────────────────────────────────────────────
# Usage example
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Full test ===")

    test_script = "test_script.R"
    with open(test_script, 'w') as f:
        f.write("""\
# R test script

process_data <- function() {
  data <- biab_inputs()

  result1 <- compute(data)
  biab_output("output1", "/tmp/file1.txt")

  result2 <- compute_more()
  biab_output("output2", "/tmp/file2.txt")

  biab_info("Processing complete")
  biab_warning("Check the results")

  info    <- c(info,    "Additional info")
  warning <- c(warning, "Another warning")

  if (length(error) > 0) {
    biab_error_stop("Fatal error occurred")
    error <- c(error, "Critical issue")
  }

  list(result1, result2)
}
""")

    try:
        print("1. Replacing biab_* functions...")
        replace_biab_functions(test_script)

        print("2. Adding inputs handling...")
        add_inputs_handling(test_script)

        print("3. Adding outputs handling...")
        replacements = {
            "output1": "/new/path/file1.txt",
            "output2": "/new/path/file2.txt",
            "output3": "/new/path/file3.txt",   # will come from output.json
        }
        add_outputs_handling(test_script, replacements)

        print(f"\n✓ File {test_script} successfully modified\n")

        with open(test_script, 'r') as f:
            print("Final content:")
            print("=" * 60)
            print(f.read())
            print("=" * 60)

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if os.path.exists(test_script):
            os.remove(test_script)
            
def find_env_vars(filepath: str) -> list[str]:
    """
    Parse an R script and return all environment variable names accessed via:
      - Sys.getenv("VAR")
      - Sys.getenv(c("VAR1", "VAR2"))
    """
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    # Remove single-line comments (# ...)
    source_no_comments = re.sub(r"#[^\n]*", "", source)

    env_vars = []

    # Match Sys.getenv("VAR") or Sys.getenv('VAR')
    single_pattern = re.compile(r'Sys\.getenv\(\s*["\']([^"\']+)["\']\s*[,)]')
    env_vars.extend(single_pattern.findall(source_no_comments))

    # Match Sys.getenv(c("VAR1", "VAR2", ...))
    c_block_pattern = re.compile(r'Sys\.getenv\(\s*c\(([^)]+)\)')
    for match in c_block_pattern.finditer(source_no_comments):
        inner = match.group(1)
        env_vars.extend(re.findall(r'["\']([^"\']+)["\']', inner))

    return set(env_vars)
