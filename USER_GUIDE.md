# Crew Monitor: User Guide

For administrators, crewing officers and managers. Labels in **bold** are the exact texts you see on screen.

---

## 1. What the system does

Crew Monitor keeps one record per seafarer, with every document the company tracks (passport, certificates of competency, medicals, endorsements and so on). For each document it shows whether it is unexpired, expiring soon or expired, whether a second person has reviewed it, and whether the issuing authority has confirmed it. It warns the right people by e-mail and in the application before a document runs out, and shows for every planned assignment whether the seafarer's documents cover it. Every change, review, download and sign-in is written to an Audit Log.

The system only advises. It never approves or blocks an assignment: crewing staff decide whether a seafarer may serve.

### Roles

| Role | What you see | What you can do |
|---|---|---|
| **Administrator** | Every seafarer, vessel and document; the whole fleet. | Everything a crewing officer can do, for all seafarers; approve accounts and give roles; manage vessels, Responsible Officers, Document Types, Positions, Requirements and Settings; search and export the Audit Log; switch the dashboard to **Fleet totals**. |
| **Crewing Officer** | Your **Scope**: the seafarers with an upcoming or under-way assignment on a vessel you are a Responsible Officer for, plus the **Unassigned Pool** (seafarers with no upcoming or under-way assignment). | Add and edit seafarers, upload documents, review and verify versions, plan assignments on your own vessels, view readiness, see alerts, download Status Reports for your vessels. |
| **Manager** | The **Dashboard** only, as fleet totals (counts, no names). | Read the fleet totals and break them down by vessel, position or document type. |

The left-hand menu shows only the pages your role can open: **Dashboard**, **Seafarers**, **Alerts**, **Vessels**, and, for administrators, an **Admin** group with **Accounts**, **Document Types**, **Positions**, **Requirements**, **Settings** and **Audit Log**. On a small screen, open the menu with the menu button in the top bar. **Sign Out** is in the top right corner.

---

## 2. Registering and signing in

Signing in always takes two steps: your password, then a **Sign-in Code** e-mailed to you. Neither alone is enough.

### Register (first time)

1. On the sign-in page, click **Register**.
2. Fill in **Full Name**, **Email**, **Password** (at least 8 characters) and **Repeat password**, then click **Create Account**.
3. We e-mail you a 6-digit code. Type it into **Sign-in Code** and click **Continue**.
4. You now see **Waiting for approval**. An administrator must approve your account and give it a role before you can use the system. Nobody picks their own role.
5. Once you are told you have been approved, click **Check again** (or sign in again).

### Sign in

1. Enter **Email** and **Password** and click **Sign in**.
2. Type the 6-digit code from the e-mail into **Sign-in Code** and click **Continue**.

About the code:

- It is valid for **10 minutes** and can be used once.
- If it does not arrive, click **Send a new code**. You can ask for a new one at most every 60 seconds (the button counts down). A new code replaces the old one.
- After 10 minutes or 5 wrong codes you must start again with your password.
- The e-mail contains only the code, never a link.
- **Back** returns you to the password step.

### Forgot password

1. On the sign-in page, click **Forgot password?**.
2. Enter your **Email** and click **Send me a code**.
3. Type the **Code** from the e-mail, choose a **New password**, repeat it in **Repeat new password** and click **Save new password**.
4. You return to the sign-in page with the message "Your password has been changed. Sign in with it now." Sign in as usual (password, then code). You are signed out everywhere else.

---

## 3. The dashboard

The **Dashboard** is your landing page.

### Administrators and crewing officers: work queues

You see work queues as tabs, each with a count. Crewing officers see the seafarers in their Scope; administrators see the whole fleet (and can switch to **Fleet totals**, see below). Entries are grouped by seafarer.

| Tab | What is in it | Button on each entry |
|---|---|---|
| **Missing** | Required documents the seafarer has no current version of (never uploaded, or every version was rejected). | **Upload** |
| **Expired** | Documents past their expiry date. | **Upload** |
| **Expiring soon** | Documents within the earliest alert step of expiry (90 days by default). | **Upload** |
| **Expiry not stated — check manually** | Documents of a type that expires, uploaded without an expiry date because none is printed on them. A person has to check them. | **Open** |
| **Waiting for review** | Documents whose current version nobody has reviewed yet. | **Review** |
| **Starting soon** | Upcoming assignments that start within the Planning Horizon (90 days by default), with counters **Before joining**, **Can be renewed at sea**, **Expiry not stated — check manually** and **Not reviewed**. | **Readiness** |
| **In order** | Documents that are unexpired or of a type with no expiry date. | **Open** |

A document can appear in two tabs, for example **Expiring soon** and **Waiting for review**.

**Filtering:**

- Type in **Filter by seafarer name**.
- Click a position, vessel or document type tag in the list to filter by it. Your filters appear as tags above the tabs; remove one with its cross, or click **Clear all**. Seafarers who are ashore are tagged **Ashore / Unassigned**.
- Tick **Show inactive** to include Inactive seafarers.
- When exactly one vessel tag is active and you may report on that vessel, a **Status Report for <vessel>** with **PDF** and **CSV** buttons appears (see section 11).

### Managers (and administrators): Fleet totals

Counts for the whole fleet, with no names: **Missing**, **Expired**, **Expiring soon**, **Unexpired**, **Expiry not stated — check manually** and **No expiry date**. Use **Break down by** to split the counts by **Vessel**, **Position** or **Document type**. Inactive seafarers are not counted. Administrators switch between the two views with **Work queues** / **Fleet totals**.

---

## 4. Seafarers

### Finding a seafarer

Open **Seafarers**. The list shows **Name**, **Position**, **Nationality**, **Current vessel** (or **Ashore**) and **Status** (**Active** / **Inactive**). Use **Search by name**; tick **Show inactive** to include Inactive seafarers. Crewing officers see only the seafarers in their Scope.

### The seafarer record

Click a name to open the record. It shows:

- **Position** (the position the seafarer holds), **Nationality**, **Date of birth** and **Current vessel** (the vessel of the assignment under way today, otherwise **Ashore**).
- A **missing documents** strip: the required documents with no current version, worked out for the vessel the seafarer is on board, or for the held position when ashore. Click a missing document's name to open the upload form with that type already chosen. If everything is there it says **No required documents missing**.
- **Assignments**, with **Plan Assignment** (section 7).
- **Documents**, with **Upload document** (section 5). The table shows **Document**, **Number**, **Expires**, **Status**, **Versions** and a **New version** button.

### Adding and editing

- **Add seafarer** (on the Seafarers page): enter **First name**, **Last name**, **Date of birth**, **Nationality** (or **Not recorded**) and **Position**. A new seafarer has no assignment, so they start in the Unassigned Pool, ashore.
- **Edit** on the record changes the same details. A promotion is recorded by editing the held **Position**; planning an assignment in another position does not change it.
- **Set Inactive** (with a **Reason**) takes the seafarer out of the working lists and stops their alerts. The record is kept. A seafarer with an upcoming or under-way assignment must have it cancelled first. **Reactivate** brings them back.

Seafarers are never deleted by hand. The records of Inactive seafarers are removed automatically once their retention period ends (section 10).

---

## 5. Documents

A **Document** is one seafarer's copy of one Document Type (for example, "Anna Petrova's passport"). A seafarer has at most one document per type. Each upload or correction creates a new **Version**; older versions stay exactly as they were. A renewal is a new version of the same document.

### Uploading

| You want to | Where | Button |
|---|---|---|
| Add a document the seafarer does not have yet | Seafarer record | **Upload document** (choose the **Document type**) |
| Upload a renewed document | Seafarer record, **Documents** table, or the document page | **New version** / **Upload new version** |
| Fix a typo in the details without a new file | Document page | **Correct details** (button **Save as new version**; it keeps the current file) |

Fill in **Document number**, **Issuing authority**, **Issue date** and, for a type that expires, **Expiry date**. If the document has no expiry date printed on it, tick **Expiry not stated on the document** instead. If the type does not expire, the form says "This document type doesn't expire." and asks for no expiry date. A type may have a maximum validity ("Valid for at most N months from the issue date."); an expiry date beyond that is refused.

Then drag the file onto the box or click to browse, and click **Upload**.

**Accepted files:**

- PDF, JPEG or PNG only (the system checks the file's content, not just its name).
- Up to **4 MB** by default (administrators can set 1–4 MB). PDFs up to **50 pages** by default. The form shows the current limits.
- PDFs with scripts, launch actions, embedded files or other active content are refused, as are password-protected or encrypted PDFs and damaged files. Images over 50 megapixels are refused.
- A refused file is not kept. The form shows the reason and keeps everything you entered, so you can fix it and try again.
- Accepted files are stored in a cleaned form (for example, photo location data is removed).

Every new version waits for review (section 6).

### The document page

Click a document's name to see its whole **History**: every version, newest first, with **Version N**, **Current**, who uploaded it and when, **Number**, **Issued by**, **Issued**, **Expires**, its **Reviews** and **Verifications**. Click the file name to open the file. The **Current** version is the newest one that has not been rejected.

### Status labels

**Expiry status** (badge on each document; shows whether or not it has been reviewed):

| Label | Meaning |
|---|---|
| **Unexpired** | Valid beyond the "expiring soon" window. |
| **Expiring soon** | Expires within the earliest alert step (90 days by default). |
| **Expired** | Past its expiry date. A document is valid through its expiry date and expired from the next day. |
| **Expiry not stated — check manually** | A type that expires, but the current version has no expiry date because none is printed on it. Someone must check it by hand. It stays this way until a version with an expiry date replaces it. |
| **No expiry date** | A Document Type that does not expire. |
| **Missing** | No current version (never uploaded, or every version rejected). |

**Endorsements**: an endorsement is valid only as long as the certificate it depends on. When the certificate runs out first you see "Valid until <date> (capped by <certificate>; own expiry <date>)". With no certificate behind it you see **Certificate missing: counts as expired**. Alerts still follow the endorsement's own expiry date.

**Review status** (per version):

| Label | Meaning |
|---|---|
| **Not reviewed** | Nobody has reviewed this version yet. On the Alerts page this shows as **Awaiting review**. |
| **Reviewed** | The latest review accepted it. |
| **Rejected** | The latest review rejected it. A rejected version is never current. |

**Verification**:

| Label | Meaning |
|---|---|
| **Verified** (shield) | The issuing authority confirmed the current version. A renewal is not verified until it is checked again. |
| **Confirmed** / **Not confirmed** | The result of each verification recorded on a version. |

"Reviewed" (a colleague checked it) and "Verified" (the issuing authority confirmed it) are different things.

**Coverage** (on the readiness view, per required document against an assignment's dates):

| Label | Meaning |
|---|---|
| **Missing** | No current version. |
| **Runs out before start** | Expires before the assignment starts. |
| **Runs out during** | Expires during the assignment, including on the planned end date. |
| **Expiry not stated — check manually** | No expiry date on the document; never counted as covering. |
| **Covers all** | Still valid after the planned end date, or of a type that does not expire. |

Coverage depends only on the expiry date, not on review or verification.

**Assignment state**: **Upcoming**, **Under way**, **Finished**, **Cancelled**.

---

## 6. Reviewing and verifying a version

### Review (accept or reject)

1. Open the document (from the **Waiting for review** tab, click **Review**).
2. In **History**, click **Review** on the version.
3. Choose **Accept** or **Reject**, write a **Comment** (required) and confirm.

Rules:

- **You cannot review a version you uploaded.** Instead of the button you see: "You uploaded this version — another account must review it."
- A decision is never edited. A later review can overturn an earlier one; the latest one counts, and earlier ones are marked **(overturned)**.
- Rejecting the current version makes the previous version that isn't rejected current again; if there is none, the document counts as missing.

### Verification (with the issuing authority)

When you have checked a document with the authority that issued it:

1. In **History**, click **Record verification** on the version.
2. Fill in **Date** (not in the future), **Result** (**Confirmed** / **Not confirmed**), **Source** (for example, "e-mail to the registry") and **Reference**. Optionally attach the proof (PDF, JPEG or PNG, same size limit).
3. Click **Record**.

The document shows **Verified** only when the latest verification of its current version is **Confirmed**.

---

## 7. Assignments and the readiness view

### Planning an assignment

On the seafarer record, click **Plan Assignment**. Choose **Vessel**, **Position**, **From** and **To (included)**, then click **Plan Assignment**.

- Crewing officers can plan, edit and cancel assignments only on vessels they are a Responsible Officer for.
- One seafarer's assignments may not overlap, and the end date can't be before the start date.
- If the position differs from the seafarer's held position, the form warns you, and the table shows "(not the held Position)".
- **Edit** changes vessel, position or dates; **Cancel** asks for a **Reason** and is permanent (the assignment is kept, marked **Cancelled**). Finished and cancelled assignments are read-only.

### Readiness

Click **Readiness** next to an upcoming or under-way assignment (on the seafarer record, the vessel page or the **Starting soon** tab). The page lists each required document for that vessel and position, with its coverage label and a suggestion (for example "Renew before joining (runs out <date>)" or "Can be renewed at sea, by <date>"). Documents are grouped:

| Group | Meaning |
|---|---|
| **Before joining** (shown as **Act now: sort out as soon as possible** once the assignment is under way) | Missing, or runs out before or during the assignment and cannot be renewed at sea. |
| **Can be renewed at sea** | Runs out during the assignment, but this type may be renewed on board. |
| **Expiry not stated — check manually** | Needs a person to check it. |
| **Uploaded, not yet reviewed** | Present but awaiting review. |
| **Covers the whole assignment** | Nothing to do. |

A missing document has an **Upload** button that opens the upload form with the type already chosen. The page also offers a **Status Report** for the assignment (**PDF** / **CSV**).

This view only advises. It approves and blocks nothing.

---

## 8. Alerts

### What triggers an alert

Every day, at the **Daily check time** in the company time zone, the system checks every document with an expiry date (required or not, reviewed or not) of every active seafarer. When a document reaches an **alert step** — by default **90, 60 and 30 days** before its expiry date, and **on the expiry day** — an alert is raised. Each step is raised only once per expiry date; if several steps are reached at once, only the most urgent one is sent.

An alert closes by itself when the document gets a new expiry date (for example, a renewal is uploaded) or the seafarer is set Inactive. Nobody closes an alert by hand.

### E-mail digests

After each daily check, each person to be warned gets **one** e-mail ("Crew Monitor: N document alerts") listing the seafarer, document, expiry date and status of each new alert, with a link to the document and to the Alerts page. Who receives it:

- The active Responsible Officers of every vessel the seafarer has an upcoming or under-way assignment on.
- The administrators, if the seafarer is in the Unassigned Pool or the vessel has no active Responsible Officer.

An e-mail that fails to send is retried at the next daily check while the alert is still open.

### The Alerts page

**Alerts** lists the open alerts in your Scope, most urgent first: **Seafarer**, **Document**, **Expiry date**, **Urgency** (for example "12 days left", "Expires today", "Expired 3 days ago"), and **Alert step** ("90 days before" or "Expiry day"). **Awaiting review** marks documents whose current version is not yet reviewed. The number next to **Alerts** in the menu is the count of open alerts.

---

## 9. Vessels and Responsible Officers

**Vessels** lists the fleet: **Name**, **IMO number**, **Flag**, **Status** (**Active** / **Deactivated**) and **Status Report** (**PDF** / **CSV**, for administrators and for the vessel's Responsible Officers). Tick **Only vessels with no active Responsible Officer** to find vessels nobody is looking after.

Click a vessel to see its details, its **Responsible Officers** and its **Crew under way and upcoming** (crewing officers see only those they are responsible for).

Administrators only:

- **Add vessel** / **Edit**: **Name**, **IMO number** (7 digits) and **Flag** (only the current flag is kept).
- **Deactivate** / **Reactivate**: a deactivated vessel and its history are kept, but it can no longer be picked for new assignments. Vessels are never deleted.
- **Responsible Officers**: pick a **Crewing officer** and click **Add Responsible Officer**, or **Remove** one. A vessel can have several officers, and an officer several vessels. A vessel with none is managed by administrators only. A switched-off officer's link shows as **Deactivated: link ignored**.

---

## 10. Administration (administrators only)

### Accounts

New sign-ups wait here until you approve them. Filter by **Pending**, **Active**, **Deactivated** or **All**; the number next to **Accounts** in the menu is the count of pending sign-ups.

- **Approve**: choose a **Role** (Administrator, Crewing Officer, Manager). For a crewing officer, tick the **Vessels (Responsible Officer)** they will look after (leave empty to start with the Unassigned Pool only). Give a **Reason**.
- **Reject** (pending sign-ups): kept as a deactivated account; it can be switched on later.
- **Change role**: changing a crewing officer's role removes their vessel links.
- **Switch off**: the person is refused and signed out on their next request. **Switch on** reverses it.

Every action needs a **Reason**, which is recorded in the Audit Log. Accounts are never deleted.

### Document Types

**Add Document Type** / **Edit** with:

- **Name**
- **Expires**: on, every document of this type needs an expiry date (or the **Expiry not stated** tick); off, it has none.
- **Maximum validity in months (optional)**: an upload whose expiry date is later than its issue date plus this is refused.
- **Renewable at sea**: advice only; used by the readiness view.
- **Depends on (makes it an Endorsement)**: the certificate this type depends on.

**Retire** hides a type from pickers and new records but keeps everything that already uses it; **Bring back** undoes that. **Delete** works only for a type that has never been used.

### Positions

**Add Position**, **Edit** (rename), **Retire** / **Bring back**, and **Delete** (only if never used).

### Requirements

Three tabs:

- **Matrix**: tick a box to require a Document Type for a Position. **Add to all positions** ticks a whole row. Retired positions and types are not shown and never count.
- **Exceptions**: **Add exception** to add or remove one Document Type for **One vessel** or **Every vessel of a flag**, for one Position or **All positions**, with a **Reason**. A vessel exception beats a flag one; one for a single Position beats one for all.
- **Preview**: pick a **Position** and optionally a **Vessel** to see exactly which documents are required, whether each comes from the **Matrix** or was **Added by an exception**, and which exceptions apply.

### Settings

Changes apply from the next request or the next daily check; click **Save settings**.

| Setting | Default | Notes |
|---|---|---|
| **Alert steps (days before expiry)** | 90, 60, 30, 0 | **Add step** / remove; **0 (expiry day)** always stays. The largest step is where "Expiring soon" begins. |
| **Planning Horizon** | 90 days | 7–365. How far ahead an assignment counts as starting soon. |
| **Maximum file size** | 4 MB | 1–4 MB. |
| **Maximum PDF pages** | 50 | 1–500. |
| **Company time zone** | UTC | Decides "today" for statuses and alerts, and how times are shown. |
| **Daily check time** | 07:00 | In the company time zone, in 15-minute steps. |
| **Retention Periods (whole years)** | Replaced Versions 5, Inactive seafarers 5, Audit Records 7 | 1–10 years. Removed automatically as the last step of the scheduled daily check. |

**Daily check → Run now** raises any alerts due, sends the digests and retries failed e-mails immediately. It does not replace today's scheduled run and never removes anything. **Last retention clean-up** shows what the latest scheduled run removed.

### Audit Log

A record of who did what and when: sign-ins and failed sign-ins, refused access, changes, reviews, verifications, file downloads, settings changes and automatic removals. Nobody can change it.

Filter by **From** / **To**, **Actor e-mail**, **Outcome** (**Succeeded** / **Refused**), **Seafarer id**, **Target type**, **Target id** and **Actions**, then click **Search** (**Clear filters** resets). Results show **When**, **Actor**, **Action**, **Outcome**, **Target** and **Details**; page with **Newer** / **Older**. **Export CSV** downloads the matching records. Searches and exports are themselves recorded.

---

## 11. Status Reports

A **Status Report** is a snapshot, as of today, of readiness — the same content as the readiness view, without document numbers or files. Download it as **PDF** or **CSV**:

- **One assignment**: on its **Readiness** page.
- **One vessel** (every assignment under way or starting within the Planning Horizon): on the **Vessels** page, or on the Dashboard when exactly one vessel filter is active.

Administrators can download any report; crewing officers only for vessels they are a Responsible Officer for. Like the readiness view, a report only advises. Each download is recorded in the Audit Log.

---

## 12. Troubleshooting and FAQ

**The Sign-in Code has not arrived.**
Wait a minute and check your spam folder. Then click **Send a new code** (available every 60 seconds); only the newest code works. If "That code is wrong or has expired" appears, send a new code. After 10 minutes or 5 wrong codes, start again with your password.

**"Too many attempts. Wait a minute, then try again."**
You asked for codes or tried passwords too quickly. Wait a minute.

**I only see "Waiting for approval".**
Your account exists but has no role yet. Ask an administrator to approve it on **Accounts**, then click **Check again**.

**I was signed out with "Your account has been switched off by an administrator".**
An administrator switched your account off. Ask them to switch it back on.

**A seafarer, page or button is missing, or I am sent back to the Dashboard.**
Each role sees only its own pages. Crewing officers see only the seafarers in their Scope: those on vessels they are a Responsible Officer for, plus the Unassigned Pool. If a seafarer is planned onto another officer's vessel, they leave your Scope. Ask an administrator to link you to the vessel. Refused attempts are recorded in the Audit Log.

**I cannot review a version.**
You uploaded it. Another account must review it.

**What does "Expiry not stated — check manually" mean?**
The document type normally expires, but this document has no expiry date printed on it, so the system cannot tell whether it is still valid and never counts it as covering an assignment. Check it by hand. It stays flagged until a version with an expiry date is uploaded. Do not invent an expiry date to clear the flag.

**My upload was refused.**
Only PDF, JPEG and PNG within the size and page limits are accepted, and PDFs must not be password-protected or contain scripts or embedded files. Save or scan the document again as a plain PDF or image and retry; the form keeps your details.

**An alert will not go away.**
Alerts close only when the document gets a new expiry date (upload the renewal) or the seafarer is set Inactive. Reviewing the document does not close it.
