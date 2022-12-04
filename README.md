# GISFAC (Generate Issue Summary For Audit Contest)

Generate a summary .csv of all the issues in the judging repo.

Used for easier QAing of audit contests like code4rena. And possibly for reward calculation.

### Setup
Rename `.env.example ` to `.env`.

Change `.env` to have the repo you want, and paste your GH classic personal access token ([generate here](https://github.com/settings/tokens)), which has `repo` access.
```
GH_API_TOKEN=YOUR_TOKEN_HERE
REPO=code-423n4/2022-10-inverse-findings
```

Then run the script.

### Known issues
- Script doesn't handle nested duplicates. Which anyway seem like a hiccup in C4's system.
For example:
     - Warden A submits issue 1, labeled as medium.
     - Warden B submits issue 2, labeled as medium.
     - Warden B submits issue 3, labeled as QA.
     - Warden A submits issue 4, labeled as QA.
     - Judge marks issue 1 with "duplicate-2" label.
     - Judge downgrades issue 2 to QA.
     - Judge marks issue 2 with "duplicate-3" label, duping to B's main QA issue. So far so good.
     - But issue 1 still has the "duplicate-2" label.

     In this scenario, the script will mark issue 1 as INVALID, as it's a duplicate of an issue which is not a main issue.
     I believe that the fundamental problem is in the repo end, and issue 1 should have been changed to be a duplicate of issue 4, as is usually done. Then the script would have handled it correctly. So the "duplicate-2" label is somewhat misleading in this scenario. We can anyway mark it as something else than INVALID but not sure what's the best way and doesn't matter too much. But open to changes.

### Future improvements / considerations
- Check if works with proof's c4-review. If not, change column names (or add option to do so) to match what c4review expects.
- At the moment the URL column is just a text url. Can we do hyperlink automatically? Probably not, so when importing to a spreadsheet, if we want a proper link column, we need to manually add a column that does `=hyperlink(G2)`, G2 being the URL.
- Add support for Sherlock repos.
- Consider changing csv filename convention, maybe this timestamp is overkill.
- There is inconsistency in the "duplicate of" column. If the issue is a duplicate of an issue with internal id, we return that id. If it is a duplicate of of an issue without internal id, we return that issue's github id. Inconsistent but dunno if there's a preferable way to show the data.