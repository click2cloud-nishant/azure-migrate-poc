from flask import Flask, render_template, request, redirect, session
import requests
import pytz  # make sure to install: pip install pytz


app = Flask(__name__)
app.secret_key = "super-secret-key"  # use env var in real apps
from flask import send_file

import openpyxl
import io
from datetime import datetime
SCOPE = "https://management.azure.com/.default"

def get_token():
    creds = session.get("creds")
    if not creds:
        return None

    url = f"https://login.microsoftonline.com/{creds['tenant_id']}/oauth2/v2.0/token"


    body = {
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "scope": SCOPE,
        "grant_type": "client_credentials"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(url, data=body, headers=headers)
    resp.raise_for_status()
    return resp.json()["access_token"]

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/set-creds", methods=["POST"])
def set_creds():
    session["creds"] = {
        "tenant_id": request.form["tenant_id"],
        "client_id": request.form["client_id"],
        "client_secret": request.form["client_secret"],
        "subscription_id": request.form["subscription_id"],
        "resource_group": request.form["resource_group"]
    }
    return redirect("/projects")

@app.route("/projects")
def list_projects():
    token = get_token()
    creds = session.get("creds")
    url = f"https://management.azure.com/subscriptions/{creds['subscription_id']}/resourceGroups/{creds['resource_group']}/providers/Microsoft.Migrate/assessmentProjects?api-version=2019-10-01"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers).json()
    projects = resp.get("value", [])

    return render_template("projects.html", projects=projects)

@app.route("/project/<project_name>")
def project_detail(project_name):
    token = get_token()
    creds = session.get("creds")
    url = f"https://management.azure.com/subscriptions/{creds['subscription_id']}/resourceGroups/{creds['resource_group']}/providers/Microsoft.Migrate/assessmentProjects/{project_name}?api-version=2019-10-01"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers).json()
    return render_template("project_detail.html", project=resp)




@app.route("/sites")
def list_sites():
    token = get_token()
    creds = session.get("creds")
    url = f"https://management.azure.com/subscriptions/{creds['subscription_id']}/resourceGroups/{creds['resource_group']}/providers/Microsoft.OffAzure/VMwareSites?api-version=2020-01-01"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers).json()
    sites = resp.get("value", [])
    return render_template("sites.html", sites=sites)




def fetch_all_pages(url, headers):
    """Fetch data from Azure API with nextLink support"""
    results = []
    while url:
        resp = requests.get(url, headers=headers).json()
        results.extend(resp.get("value", []))
        url = resp.get("nextLink")  # follow pagination
    return results


@app.route("/machines/<site_name>")
def list_machines(site_name):
    token = get_token()
    creds = session.get("creds")
    url = f"https://management.azure.com/subscriptions/{creds['subscription_id']}/resourceGroups/{creds['resource_group']}/providers/Microsoft.OffAzure/VMwareSites/{site_name}/machines?api-version=2020-01-01"
    headers = {"Authorization": f"Bearer {token}"}

    machines = fetch_all_pages(url, headers)
    print("Machines", machines)
    # --- Search & Filter ---
    search = request.args.get("search", "").lower()
    status_filter = request.args.get("status", "")

    if search:
        machines = [m for m in machines if search in (m["properties"].get("displayName", "").lower() or m.get("name", "").lower())]

    if status_filter:
        machines = [m for m in machines if m["properties"].get("powerStatus", "N/A") == status_filter]

    # --- Pagination ---
    page = int(request.args.get("page", 1))
    per_page = 10
    total = len(machines)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = machines[start:end]

    total_pages = (total + per_page - 1) // per_page  # ceil division

    # --- Last refresh timestamp ---
    ist = pytz.timezone("Asia/Kolkata")
    last_refresh = datetime.now(ist).strftime("%Y-%m-%d %I:%M:%S %p IST")

    return render_template(
        "machines.html",
        machines=paginated,
        site_name=site_name,
        page=page,
        total_pages=total_pages,
        total=total,
        last_refresh=last_refresh
    )



# @app.route("/machines/<site_name>/export")
# def export_machines(site_name):
#     token = get_token()
#     creds = session.get("creds")
#     url = f"https://management.azure.com/subscriptions/{creds['subscription_id']}/resourceGroups/{creds['resource_group']}/providers/Microsoft.OffAzure/VMwareSites/{site_name}/machines?api-version=2020-01-01"
#     headers = {"Authorization": f"Bearer {token}"}
#
#     machines = fetch_all_pages(url, headers)
#
#     # --- Create Excel workbook ---
#     wb = openpyxl.Workbook()
#     ws = wb.active
#     ws.title = "VM"
#
#     # Header row (as per your screenshot)
#     ws.append([
#         "MACHINE NAME", "CPU", "RAM (MB)", "OS",
#         "STANDARD HDD SIZE (GB)", "STANDARD SSD SIZE (GB)", "PREMIUM DISK (GB)",
#         "CPU USAGE (%)", "MEMORY USAGE (%)", "VIRTUALIZATION PLATFORM"
#     ])
#
#     for m in machines:
#         props = m.get("properties", {})
#
#         # --- Extract Disks ---
#         hdd_size = 0
#         ssd_size = 0
#         premium_size = 0
#         if props.get("disks"):
#             for d in props["disks"]:
#                 size_gb = round(d.get("maxSizeInBytes", 0) / (1024*1024*1024), 1)
#                 policy = d.get("diskProvisioningPolicy", "").lower()
#                 if "standard" in policy and "ssd" not in policy:
#                     hdd_size += size_gb
#                 elif "standardssd" in policy or "ssd" in policy:
#                     ssd_size += size_gb
#                 elif "premium" in policy:
#                     premium_size += size_gb
#
#         # --- Other fields ---
#         name = props.get("displayName", m.get("name"))
#         os = props.get("operatingSystemDetails", {}).get("osName", "N/A")
#         cpu = props.get("numberOfProcessorCore", "N/A")
#         ram = props.get("allocatedMemoryInMB", "N/A")
#         cpu_usage = props.get("cpuUtilizationPercentage", 0)
#         mem_usage = props.get("memoryUtilizationPercentage", 0)
#         virt = props.get("virtualizationPlatform","N/A")
#
#         ws.append([
#             name, cpu, ram, os,
#             hdd_size, ssd_size, premium_size,
#             cpu_usage, mem_usage, virt
#         ])
#
#     # Save to memory
#     output = io.BytesIO()
#     wb.save(output)
#     output.seek(0)
#
#     return send_file(
#         output,
#         as_attachment=True,
#         download_name=f"{site_name}_machines.xlsx",
#         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#     )




@app.route("/machines/<site_name>/export")
def export_machines(site_name):
    token = get_token()
    creds = session.get("creds")
    url = f"https://management.azure.com/subscriptions/{creds['subscription_id']}/resourceGroups/{creds['resource_group']}/providers/Microsoft.OffAzure/VMwareSites/{site_name}/machines?api-version=2020-01-01"
    headers = {"Authorization": f"Bearer {token}"}

    machines = fetch_all_pages(url, headers)

    # --- Create Excel workbook ---
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "VM"

    # Header row (added TOTAL STORAGE column)
    ws.append([
        "MACHINE NAME", "CPU", "RAM (MB)", "OS",
        "TOTAL STORAGE (GB)",
        "CPU USAGE (%)", "MEMORY USAGE (%)", "VIRTUALIZATION PLATFORM"
    ])

    for m in machines:
        props = m.get("properties", {})

        # --- Calculate Total Storage ---
        total_storage = 0
        if props.get("disks"):
            for d in props["disks"]:
                size_gb = round(d.get("maxSizeInBytes", 0) / (1024*1024*1024), 1)
                total_storage += size_gb

        # --- Other fields ---
        name = props.get("displayName", m.get("name"))
        os = props.get("operatingSystemDetails", {}).get("osName", "N/A")
        cpu = props.get("numberOfProcessorCore", "N/A")
        ram = props.get("allocatedMemoryInMB", "N/A")
        cpu_usage = props.get("cpuUtilizationPercentage", 0)
        mem_usage = props.get("memoryUtilizationPercentage", 0)
        virt = props.get("virtualizationPlatform","N/A")

        ws.append([
            name, cpu, ram, os,
            total_storage,
            cpu_usage, mem_usage, virt
        ])

    # Save to memory
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f"{site_name}_machines.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )




if __name__ == "__main__":
    app.run(debug=True)
