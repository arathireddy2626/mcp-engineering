# MCP Server for Engineering Automation

A Python-based Model Context Protocol (MCP) server and minimal CLI client designed for engineering automation tasks. This project demonstrates dynamic interaction between client and server, utilizing a local SQLite database for mocked users and data. It focuses on tool contracts, explicit schemas, and deterministic behavior over broad functionality.

## Features

* **Model Context Protocol (MCP):** Exposes distinct tools and prompts for AI agent interaction.
* **Explicit Schemas & Validation:** Leverages `pydantic` for strict input validation and explicit tool contracts.
* **Clear Operation Boundaries:** Strict separation of read vs. write operations to prevent unsafe or destructive actions.
* **Minimal Client:** Includes a thin CLI client that accepts natural language instructions and executes MCP tool calls.
* **Asynchronous Database:** Uses `aiosqlite` for non-blocking local database interactions.
* **Testable & Deterministic:** Includes a robust `pytest` suite ensuring consistent agent and tool behavior.

## Project Structure

```text
mcp-engineering/
├── client/               # Minimal CLI client implementation
│   └── cli.py            # Command-line interface entry point
├── server/               # MCP Server application
│   ├── main.py           # Server entry point and configuration
│   ├── db.py             # Database connection and queries
│   ├── models.py         # Pydantic schemas and data models
│   ├── tools.py          # MCP tool definitions and read/write operations
│   └── elicitation.py    # Prompt and context management
├── scripts/
│   └── seed.py           # Script to initialize and seed the database
├── tests/                # Pytest test suite
│   ├── test_dispatcher.py
│   ├── test_models.py
│   └── test_tools.py
├── docs/                 # Project documentation and technical reports
├── engineering.db        # Local SQLite database
├── pytest.ini            # Pytest configuration
├── requirements.txt      # Production dependencies
└── requirements-dev.txt  # Development dependencies

```

## Dependencies

This project runs on Python 3.14 (virtual environment included) and utilizes the following primary packages:

* `mcp[cli] >= 1.9.0`
* `aiosqlite >= 0.20.0`
* `pydantic >= 2.7.0`

## Installation

1. **Clone the repository and navigate to the directory:**
```bash
git clone <repository-url>
cd mcp-engineering

```


2. **Create and activate a virtual environment:**
```bash
python -m venv .venv

# On Windows:
.venv\Scripts\activate

# On macOS/Linux:
source .venv/bin/activate

```


3. **Install dependencies:**
```bash
pip install -r requirements.txt

```


4. **Initialize the Database:**
Seed the local SQLite database with mock data before your first run.
```bash
python scripts/seed.py

```



## Usage

**Starting the MCP Server**
Run the server to initialize the database connection and expose tools to the client:

```bash
python -m server.main

```

**Using the Minimal Client**
Execute the CLI client to interact with the server using natural language:

```bash
python -m client.cli "Your natural language instruction here"

```

## Testing and Debugging

This project uses `pytest` to ensure deterministic behavior, validate schemas, and test tool failure modes. To run the test suite:

```bash
pip install -r requirements-dev.txt
pytest

```
