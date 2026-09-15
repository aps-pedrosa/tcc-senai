# VoidLog

A full-stack warehouse and equipment management system developed as a **Final Course Project for the SENAI Technical Course in Systems Development**.

The project was designed to provide a centralized platform for managing equipment, operators, inventory movements, maintenance operations, and warehouse infrastructure. It also integrates with **ESP32-based terminals and RFID identification**, connecting physical warehouse operations with the software system.

---

## Overview

The system provides a web-based interface for monitoring and managing warehouse operations in real time.

Its architecture combines a **Python/Flask backend**, a relational database, a browser-based dashboard, and hardware terminals used for physical identification and equipment interactions.

The project was developed with the goal of applying software development concepts to a practical industrial logistics scenario, including:

* Inventory and equipment management
* Operator identification
* Equipment check-in and check-out
* Warehouse and sector organization
* Maintenance tracking
* User authentication and access control
* RFID-based identification
* ESP32 terminal integration
* Operational dashboards
* Data export and reporting
* Real-time event updates

---

## Key Features

### Equipment Management

Manage the complete lifecycle of warehouse equipment and assets, including:

* Equipment registration
* Categories and descriptions
* Quantity and weight information
* Availability status
* Current location
* Last movement
* Maintenance status
* Operator association
* Unique RFID identifiers

### Movement Tracking

The system records equipment movements between warehouse operations, providing an operational history of:

* Equipment withdrawals
* Equipment returns
* Responsible operator
* Terminal used
* Sector and unit
* Timestamp

This creates an auditable history of equipment utilization.

### Maintenance Management

Equipment can be placed into and removed from maintenance status while recording:

* Maintenance type
* Description
* Responsible technician
* Equipment
* Terminal
* Timestamp

### Operator Management

Operators are associated with equipment and identified through unique credentials/RFID identifiers.

The system maintains operator information such as:

* Name
* Registration number
* RFID UID
* Associated equipment

### Authentication & Access Control

The web dashboard includes authenticated users with role-based access levels:

* **Administrator**
* **Operator**
* **Viewer**

Login activity is also recorded for auditing purposes.

### RFID & ESP32 Integration

The system extends beyond a traditional web application by integrating physical hardware into the warehouse workflow.

ESP32 terminals can interact with the backend to support physical identification and equipment operations through RFID.

This creates a bridge between:

<img width="2006" height="152" alt="mermaid-diagram" src="https://github.com/user-attachments/assets/3907e16b-66e3-4aad-894d-43ff80921ec8" />

### Real-Time Updates

The application implements **Server-Sent Events (SSE)** to broadcast events from the backend to connected clients without requiring constant page refreshes.

This allows the dashboard to react to operational changes as they occur.

### Reporting & Export

Operational data can be exported for further analysis and reporting, including:

* CSV exports
* PDF exports
* Filtered datasets
* Export history

---

## Technology Stack

### Backend

* **Python**
* **Flask**
* REST-style API endpoints
* Server-Sent Events (SSE)
* Modular Flask Blueprints

### Database

* **SQLite**
* Relational data model
* Foreign-key relationships
* Database migrations

The database models the main entities of the system, including equipment, operators, sessions, movements, maintenance records, users, terminals, exports, and system configuration.

### Hardware

* **ESP32**
* RFID identification

### Frontend

* HTML
* CSS
* JavaScript
* Flask/Jinja templates

---

## Database Model

The system maintains relationships between the main operational entities:

<img width="1921" height="1872" alt="mermaid-diagram(2)" src="https://github.com/user-attachments/assets/f86d8432-0588-40c5-baca-d937c1e2ac71" />

The database also includes migration logic, allowing the schema to evolve as the project develops.

---

## Running Locally

### Requirements

* Python 3.x
* pip
* ESP32 hardware is optional for running the web application

### Installation

Clone the repository:

```bash
git clone https://github.com/aps-pedrosa/tcc-senai.git
cd tcc-senai
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```powershell
.venv\Scripts\activate
```

Or on Linux/macOS:

```bash
source .venv/bin/activate
```

Install the project dependencies:

```bash
pip install -r requirements.txt
```

Start the application:

```bash
python app.py
```

The application will be available at:

```text
http://localhost:5000
```

> **Note:** If the dependency list or configuration requirements change, refer to the current project files before deployment.

---

## Project Context

This system was developed as the **Final Course Project (TCC)** for the SENAI Technical Program in Systems Development.

The project served as an opportunity to apply software engineering concepts to a practical industrial problem, combining:

* Backend development
* Database design
* Web application development
* API design
* Authentication
* Hardware integration
* RFID technology
* Real-time communication
* Data management
* System architecture

Rather than functioning only as an academic CRUD application, the project was designed around an operational workflow where **software and physical warehouse infrastructure interact as part of the same system**.

---

## Learning Outcomes

The project provided practical experience with:

* Designing relational databases
* Developing modular backend applications with Flask
* Building REST-style APIs
* Implementing authentication and authorization
* Managing persistent application state
* Integrating software with microcontrollers
* Working with RFID identification
* Designing real-time communication using SSE
* Structuring a multi-module application
* Implementing database migrations
* Building operational dashboards
* Generating data exports

---

## Status

This repository represents the final state of the project developed during the technical program.

It is primarily preserved as a **portfolio and educational project**, documenting the software architecture and technologies used during its development.

---

## Author

**Pedrosa**

Technical background in **Systems Development and Mechatronics**, with interests in software engineering, industrial automation, embedded systems, and the integration of software with physical systems.

---

## License

This project was developed as an academic project. See the repository for the applicable licensing and usage information.
