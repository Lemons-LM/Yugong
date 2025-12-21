# YuGong Bot

## Project Overview

YuGong is a Python-based automated wiki editing tool designed to help users batch process page content on specific wiki sites. The project provides a flexible extension mechanism that allows users to customize various template processing tasks.

## Core Features

- **Automated Wiki Editing**: Supports batch page processing on specified wiki sites
- **Task Processing**: Support template (`{{}}`), link(`[[]]`/`[]`) and tags (<foo>)
- **Safety First**: If something might lead to vandalism, make the entire program doesn't work. 
- **Extensible Architecture**: Tasks are registered through the `Extensions` directory
- **Safety Controls**: Built-in risk control mechanisms including diff size checking and dangerous tag detection
- **Chinese Conversion**: Cangjie auto convert zh-Hans <=> zh-Hant, and other varients, via NoteTA so make sure no wrong convertions.

## Installation and Configuration

### Requirements

- Python 3.12+
- Related dependency packages (dependencies to be added)

### Installation Steps

1. Clone the project repository
2. Install the dependency environment
3. Configure [LocalSettings.txt](LocalSettings.txt)
4. Run:
```shell
cd path_to_project
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

### Configuration Guide

Set necessary parameters in [LocalSettings.txt](LocalSettings.txt):

```txt
# Wiki Settings
api_endpoint=          # Wiki API endpoint, REQUIRED
user_agent=           # Request User-Agent
is_owner_only=        # Whether to enable owner protection mode
client_id=            # OAuth client ID

# Task Settings (At lease fill one of them)
page_id_start=        # Starting page ID
page_id_end=          # Ending page ID
linked_template=      # Target template to process
category=             # Working category

# Behavior Settings
risk_level=           # Risk control level, or one of the four below
overwrite_para_name=  # Auto change the parameters' names to the preferred ones defined in extensions
overwrite_template_name= # Auto change the template's name to the preferred one defined in extensions
is_dangerous_tag_unacceptable= # If something like `<big><big><big>something</big></big></big>` or `<div style="wt*isit: bar">`, shall the program throw an error and skip/exit
max_acceptable_diff_size= # compare the raw wikitext and the final one, how much diff it makes
enable_cangjie=       # Whether to enable Cangjie varients conversion
```


## Extension Development

### Creating New Extensions

Follow these steps to create custom extensions:

1. Copy [example.py](src/Yugong/Extensions/example.py) in the `Extensions` directory and rename it
2. Modify the function name and task definition
3. Implement specific template processing logic
4. Add task introduction description

## Usage Workflow

1. **Initialization Confirmation**: User confirms understanding of usage responsibilities
2. **Configuration Loading**: Read and validate [LocalSettings.txt](LocalSettings.txt) configuration
3. **Task Preview**: Display all extension task descriptions
4. **Execution Processing**: Connect to wiki instance and execute processing
5. **Result Output**: Show processing results and provide follow-up actions:
   1. **Current (MVP phase)**: After processing a page, copy the text to the clipboard, open a page in the browser and let the user paste and submit manually
   2. **Target**: Auto submit or after a human review on diff

## Safety Mechanisms

- **User Confirmation**: Mandatory user confirmation of responsibilities and configurations
- **Risk Control**: Configurable risk level controls
- **Diff Checking**: Validation of edit differences before and after
- **Dangerous Tag Detection**: Identification and handling of unsafe HTML tags
- **Strong Data Type/Checking**: Make sure no error on input data

## Important Notes

**Important Reminder**:
- This software is provided "as is" without warranty of any kind
- Users bear full responsibility for usage
- Must ensure usage complies with all applicable laws and regulations in your jurisdiction
- Including but not limited to the laws of the People's Republic of China

## Contributing
Contributions are welcome, as long as follow the [legal terms](LEGAL.md). Please read [CONTRIBUTING.md](CONTRIBUTING.md).