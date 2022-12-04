import requests
import csv
from dotenv import dotenv_values
from datetime import datetime

csv_delimiter = "|"

config = dotenv_values(".env")
api_token = config["GH_API_TOKEN"]
repo = config["REPO"]
ag_and_di_label = "Agreements & Disclosures"

# For GH labels like "duplicate-23", will extract the primary issue - eg. return 23
#   example for dup label:
#   {'name': 'duplicate-49', 'id': 4821270416, 'node_id': 'LA_kwDOIZUCps8AAAABH16_kA', 'url': 'https://api.github.com/repos/code-423n4/2022-11-stakehouse-findings/labels/duplicate-49', 'color': 'E13445', 'default': False, 'description': None}
def extract_primary_from_duplicate_label(labels):
    dup_label = [x for x in labels if "duplicate-" in x]
    if (len(dup_label) == 0):
        return ""
    # Does this function return string? Does it return int? Who cares! This is python! 👑
    return int(dup_label[0].split("duplicate-")[1])

# Convert labels like "3 (High Risk)" to "High". EXTREMELY important and sensitive functionality.
def extract_severity_from_label(labels):
    if (len([x for x in labels if "High Risk" in x]) > 0):
        return "High"
    if (len([x for x in labels if "Med Risk" in x]) > 0):
        return "Medium"
    if (len([x for x in labels if "Quality Assurance" in x]) > 0):
        return "QA"
    if (len([x for x in labels if "Gas Optimization" in x]) > 0):
        return "Gas"

# Convert TMI GH labels response to a cute list of labels 🥰
def get_all_labels(issue):
    return [x["name"] for x in issue["labels"]]

# DOES IT??\
def does_label_exist(labels, label):
    return (len([x for x in labels if label in x]) > 0)

# Unsatisfactory or nullified labels will mark an issue as invalid.
def is_invalid(labels):
    return (does_label_exist(labels, "unsatisfactory") or does_label_exist(labels, "nullified"))

# If issue has label partial-75, he will get 75/100 of the score. So return 0.75.
def extract_partial_scoring(labels):
    partial_label = [x for x in labels if "partial-" in x]
    if (len(partial_label) == 0):
        return 0
    return (float(partial_label[0].split("partial-")[1]) / 100)

def getFromGithub(endpoint, _query_params):
    curr_page = 1
    header_params = {"Authorization": "Bearer " + api_token, "Accept": "application/vnd.github+json"}
    query_params = {"page": curr_page, "per_page": "100"}
    query_params.update(_query_params)
    api_url = "https://api.github.com/repos/" + repo + endpoint
    result = []
    while True:
        response = requests.get(api_url, headers=header_params, params=query_params)
        if (response.json() == []): # if we exhausted all issues, stop querying.
            break
        result += response.json()
        curr_page += 1
        query_params.update({"page": curr_page})
    return result



################
## Start main ##
################

print("Creating issue summary spreadsheet for repo " + repo + ".")

# Get all issues from GH
print("Fetching all issues from GitHub...")
issues = getFromGithub("/issues", { "state": "all" })

# Get all commits from GH
print("Fetching all commits from GitHub...")
commits = getFromGithub("/commits", {})

print("Parsing data...")

# Use commits to extract the author for each issue
issue_author = {}
for commit in commits:
    message = commit["commit"]["message"]
    # Skip unrelevant commits
    if "data for issue" in message or "updated by" in message or "withdrawn by" in message:
        continue
    split = message.split(" issue #")
    # Try to get only original issue commits
    if len(split) == 2:
        issue_author[int(split[1])] = split[0]

# Create internal ids for all primary issues
# Can't use "primary" label as some primary issues (solos?) do not get that tag.
issue_severities = {} # { githubId: severity } , will be used later to set duplicates severities to main issue's severity
issue_internal_ids = {} # { githudId: internalId }
main_issues_id_counter = {"High": 1, "Medium": 1, "QA": 1, "Gas": 1} # Enumerate num of issues
main_issues = set()
for issue in issues:
    id = issue["number"]
    labels = get_all_labels(issue)
    severity = extract_severity_from_label(labels)
    # Following conditional checks whether the issue is a primary issue.
    if not (is_invalid(labels) or does_label_exist(labels, "withdrawn") or does_label_exist(labels, "duplicate") \
        or issue["title"] == ag_and_di_label):
        main_issues.add(id)
        issue_severities[id] = severity
        issue_internal_ids[id] = severity[:1] + "-" + str(main_issues_id_counter[severity]).zfill(3) # eg. H-23 or M-05
        main_issues_id_counter[severity] += 1

# Categorize all non-primary issues
for issue in issues:
    id = issue["number"]
    labels = get_all_labels(issue)
    if id in main_issues:
        # Already done in previous loop
        continue
    elif does_label_exist(labels, "withdrawn by warden"):
        issue_severities[id] = "WITHDRAWN"
        issue_internal_ids[id] = "WITHDRAWN"
    elif is_invalid(labels):
        issue_severities[id] = "INVALID"
        issue_internal_ids[id] = "INVALID"
    elif does_label_exist(labels, "duplicate"):
        primary = extract_primary_from_duplicate_label(labels)
        if primary in main_issues:
            # Current issue is duplicate of an accepted issue. Set current issue's severity and internal id
            #   to be main issue's severity and internal id.
            issue_severities[id] = issue_severities[primary]
            issue_internal_ids[id] = issue_internal_ids[primary]
        else:
            # Issue is a duplicate of a not accepted issue.
            issue_severities[id] = "INVALID"
            issue_internal_ids[id] = "INVALID"
    else:
        # Catch edge cases
        issue_severities[id] = "UNKNOWN"
        issue_internal_ids[id] = "UNKNOWN"

# Prepare final csv data
severity_sorting = {"High": 0, "Medium": 1, "QA": 2, "Gas": 3, "INVALID": 4, "WITHDRAWN": 5, "UNKNOWN": 6}
csv_headers = ["github id", "internal id", "duplicate of", "title", "warden", "weight", "severity", "url", "labels"]
parsed_list = []
for issue in issues:
    if issue["title"] == ag_and_di_label: # Skip the Agreements & Disclosures issue
        continue
    id = issue["number"]
    labels = get_all_labels(issue)
    # Calculate "duplicate off" field. See README.MD for notes on inconsistency here.
    dup_of = extract_primary_from_duplicate_label(labels)
    if dup_of in main_issues:
        dup_of = issue_internal_ids[dup_of]

    author = issue_author[id] if id in issue_author else ""
    
    # Calculate issue weight: normal issues get 1, selected for report gets 1.3, partial-x gets x/100
    weight = ""
    if not (issue_severities[id] == "INVALID" or issue_severities[id] == "WITHDRAWN"):
        weight = 1
        if (does_label_exist(labels, "selected for report")):
            weight = 1.3
        elif extract_partial_scoring(labels) != 0:
            weight = extract_partial_scoring(labels)

    # Create a column to sort by severity -> internalID -> isPrimary? -> author
    # Might be "cleaner" to do it outside, but here we get the field names,
    #   and afterwards this will be just a list without convenient field names
    sorting_field = str(severity_sorting[issue_severities[id]]) + issue_internal_ids[id] + \
        ("a" if int(id) in main_issues else "b") + author
    
    # Actual final parsed issue for CSV
    curr_issue = [[id, issue_internal_ids[id], dup_of , issue["title"], author, weight, issue_severities[id], \
        issue["html_url"], labels, sorting_field]]
    parsed_list += curr_issue

# Sort list, then remove sorting column
parsed_list.sort(key=lambda x: x[-1])
parsed_list = [x[:-1] for x in parsed_list]

# Write to file. Using timestamp in filename to not overwrite previous data. Probably unnecessary 🙂
# Filename example: 2022-11-non-fungible-findings--04-12-2022--10-01-59.csv
filename = repo.split("/")[1] + "--" + datetime.now().strftime("%d-%m-%Y--%H-%M-%S") + ".csv"
with open(filename, "w") as f:
    write = csv.writer(f, delimiter=csv_delimiter);
    write.writerow(csv_headers)
    write.writerows(parsed_list)

print("Done! Wrote " + str(len(parsed_list)) + " issues to: " + filename)