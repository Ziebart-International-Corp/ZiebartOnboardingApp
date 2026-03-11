# API-only migration: remaining work by section

Do these **one section at a time**. Each section is a logical chunk (one area of the app or one model). Finish reads for a section before moving to the next; writes can be a final section or handled per-section if you add API write endpoints.

---

## Section 1: New Hires list and dashboard (read-only)

**Goal:** All reads of new hires (list, count, filter by store/status) go through data_layer. No `NewHire.query` for reads.

**Already done:**  
- Manager dashboard new_hires count and documents count (when USE_DATA_API).  
- Stats block: `list_new_hires_filtered(status_exclude='removed')` and training progress via API.

**Remaining in app.py:**

| Location (approx) | Current code | Change to |
|-------------------|--------------|-----------|
| ~4029 `_view_all_new_hires_impl` | `q = NewHire.query.filter(NewHire.status != 'removed')`, then store filter, then `.all()`, loop uses `new_hire.required_training_videos` | Use `data_layer.list_new_hires_filtered(status_exclude='removed')`, filter by `store_id` in Python if manager. In loop, use `data_layer.get_new_hire_required_video_ids(nh.id)` and `data_layer.list_user_training_progress(username, video_id)` instead of `required_training_videos`. |
| ~4058 | `NewHireChecklist.query.filter_by(new_hire_id=..., is_completed=True).count()` | Add data_layer/API for “checklist completed count by new_hire_id” (or stub 0 when USE_DATA_API until Section 8). |
| ~6819 | Already using list_new_hires_filtered for count | — |
| ~8586 (manage documents) | `NewHire.query.filter_by(store_id=store_id).all()` for `store_usernames` | `data_layer.list_new_hires_filtered(status_exclude='removed')` then filter in Python by `store_id`; build `store_usernames` from that. |
| ~18122 | `q = NewHire.query.filter(NewHire.status != 'removed')`, store filter, `.all()`, then UserModel.query per nh | Use list_new_hires_filtered + store filter; use `data_layer.get_user(nh.username)` instead of UserModel.query. |

**Data API / api_client / data_layer:**  
- Optional: endpoint to list new hires with optional `store_id` and `status_exclude` so you don’t filter large lists in Python.  
- Checklist completed count: add in Section 8 or stub for now.

**Done when:** No `NewHire.query` left for reads (only in migration helpers that already return early when USE_DATA_API).

---

## Section 2: Documents – manage documents page and archived list (read-only)

**Goal:** Document list (active + archived), archived count, and per-doc signature counts use data_layer/API only.

**Already done:**  
- Active document list for manage documents uses `documents_visible_to_store_query` (which uses data_layer when USE_DATA_API).  
- `list_documents_visible_to_store(store_id)` in data_layer.

**Remaining in app.py (this section):**

| Location (approx) | Current code | Change to |
|-------------------|--------------|-----------|
| ~8533, 8575, 8568, 8612 | `Document.query` for archived list (`deleted_at.isnot(None)`), archived count `qa.count()`, fallback document lists | Add data_layer: `list_documents(archived_only=True)` or param on list_documents; `count_documents(archived_only=True)`. Use these when USE_DATA_API; keep existing query when not. |
| ~8594 | `DocumentSignature.query.filter_by(document_id=doc.id).all()` for signature counts | Add API: list signatures by document_id (or count). Add data_layer `list_document_signatures(document_id)` / `count_document_signatures(document_id)`. Use in loop instead of DocumentSignature.query. |

**Data API:**  
- GET `/documents?archived_only=true` (or `deleted_at_null=false`) and optionally `store_id` for manager.  
- GET `/documents/<id>/signatures` or `/document-signatures?document_id=...` (list or count).

**api_client / data_layer:**  
- `list_documents(..., archived_only=True)`, `count_documents(archived_only=True)` (if you want count without loading list).  
- `list_document_signatures(document_id)` or `count_document_signatures(document_id)`.

**Done when:** Manage documents page and its archived view/count and per-doc signature counts use only data_layer (no direct Document.query / DocumentSignature.query for these paths).

---

## Section 3: Documents – dashboard and other Document.query (read-only)

**Goal:** Every other read that uses `Document.query` goes through data_layer (list_documents, list_documents_visible_to_store, get_document).

**Remaining in app.py (this section):**

| Location (approx) | Current code | Change to |
|-------------------|--------------|-----------|
| ~1141, 1145 | Dashboard: `Document.query.filter(...).limit(3).all()` for visible_documents | Use `data_layer.list_documents_visible_to_store(store_id)` or `list_documents(...)` and slice to 3; or add `limit` param to API. |
| ~469 (documents_visible_to_store_query) | Non-API branch still uses Document.query | Already split; no change if Section 2 didn’t touch it. |
| ~5504 | `Document.query.join(DocumentSignatureField).distinct().all()` (documents_with_signatures) | Add API: documents that have at least one signature field (or use list_documents + filter by list_document_signature_fields). data_layer: `list_documents_with_signature_fields()`. |
| ~7204, 7293 | Store detail: `Document.query.filter_by(store_id=...).count()` and `.all()` for forms | data_layer: `list_documents(store_id=store_id)` and len for count (or add count endpoint). |
| ~11984, 11990, 12013, 12017 | Assignment flows: Document.query for list by ids or all | Use `data_layer.list_documents()` and filter by id in Python, or add list_documents by id list; use `data_layer.get_document(id)` in loops as needed. |
| ~18374 | `Document.query.order_by(...).all()` | Replace with `data_layer.list_documents()` (with appropriate filters/ordering in API). |
| ~20453, 20477, 20478 | Stats: Document count, visible count, documents_with_signatures count | data_layer/API: count_documents(), count_documents(visible_only=True), count_documents(with_signature_fields=True) or derive from lists if small. |

**Data API / api_client / data_layer:**  
- Optional: `list_documents(store_id=...)`, `count_documents(...)`, “documents with signature fields” (filter or dedicated endpoint).  
- Use existing `list_documents_visible_to_store`, `list_documents`, `get_document` where they fit.

**Done when:** No remaining `Document.query` for reads outside migration helpers (which already skip when USE_DATA_API).

---

## Section 4: Users and stores (read-only)

**Goal:** All user and store reads go through data_layer: get user by id, list users by store/role, store detail counts.

**Remaining in app.py (this section):**

| Location (approx) | Current code | Change to |
|-------------------|--------------|-----------|
| ~7202, 7203 | `UserModel.query.filter_by(store_id=store.id, role='manager').count()` and same for role='user' | data_layer: e.g. `count_users(store_id=..., role='manager')` and same for 'user'. |
| ~7291, 7292 | `UserModel.query.filter_by(store_id=store_id, role='manager').all()` and `.filter_by(..., role='user').all()` | data_layer: `list_users(store_id=..., role='manager')` and `list_users(store_id=..., role='user')`. |
| ~7404, 7408 | `UserModel.query.filter(UserModel.role.in_(['user', 'manager'])).all()` | data_layer: `list_users(roles=['user', 'manager'])` or list_users and filter in Python. |
| ~7703, 7740, 7762, 7793, 8090, 8457, 8479, 8503 | `UserModel.query.get(user_id)` | data_layer: `get_user_by_id(user_id)` (add API endpoint and data_layer). |
| ~8110 | `UserModel.query.filter_by(role='admin').all()` | data_layer: `list_users(role='admin')` or filter list_users. |
| ~11525 | `UserModel.query.order_by(UserModel.username).all()` | data_layer: `list_users()` (already exists). |

**Data API:**  
- GET `/users/{user_id}` (by id).  
- GET `/users` with optional query params: `store_id`, `role` (or `roles`).  
- Optional: GET `/users/count` with `store_id`, `role` (you may already have count).

**api_client / data_layer:**  
- `get_user_by_id(user_id)`.  
- `list_users(store_id=..., role=...)`, `count_users(store_id=..., role=...)` if not already present.

**Done when:** No `UserModel.query` for reads in these routes; store detail and user management reads use data_layer only.

---

## Section 5: Training progress (read-only)

**Goal:** All reads of `UserTrainingProgress` go through data_layer (`list_user_training_progress`).

**Remaining in app.py (this section):**

| Location (approx) | Current code | Change to |
|-------------------|--------------|-----------|
| ~983 | `UserTrainingProgress.query.filter_by(username=..., video_id=..., is_completed=True, is_passed=True).first()` | data_layer: `list_user_training_progress(username, video_id=video_id)` then check for completed+passed in Python. |
| ~2433, 2525 | Same pattern in task/onboarding creation | Same: use list_user_training_progress and check in Python. |
| ~4043 | Same in _view_all_new_hires_impl | Same (or already fixed in Section 1). |

**Data API / data_layer:**  
- `list_user_training_progress(username, video_id=...)` already exists; ensure response includes `is_completed`, `is_passed`.

**Done when:** No `UserTrainingProgress.query` for reads.

---

## Section 6: Document signatures and notifications (read-only)

**Goal:** All reads of `DocumentSignature`, `UserNotification`, `ExternalLink` go through data_layer.

**Remaining in app.py (this section):**

| Location (approx) | Current code | Change to |
|-------------------|--------------|-----------|
| ~787, 802 | `DocumentSignature.query.filter_by(...)` (orphaned sigs, etc.) | data_layer: e.g. `list_document_signatures(document_id=...)` or by signature_field_id; implement in API + data_layer. |
| ~1081, 1103 | `UserNotification.query.filter_by(...)` | data_layer: `get_user_notification(...)` or `list_user_notifications(username, ...)`; add API + data_layer. |
| ~11486 | `DocumentSignature.query.filter_by(signature_field_id=field_id).all()` | data_layer: `list_document_signatures(signature_field_id=field_id)`. |
| ~1151 | `ExternalLink.query.filter_by(is_active=True).order_by(...).all()` | data_layer: `list_external_links(active_only=True)`; add API + data_layer. |
| ~5571 | `UserNotification.query.filter_by(...)` | Same as above. |

**Data API:**  
- GET `/document-signatures?document_id=...` and/or `?signature_field_id=...`.  
- GET `/user-notifications` (e.g. by username, read/unread).  
- GET `/external-links?is_active=true`.

**api_client / data_layer:**  
- `list_document_signatures(document_id=..., signature_field_id=...)`.  
- `list_user_notifications(username, ...)`, `get_user_notification(...)` as needed.  
- `list_external_links(active_only=True)`.

**Done when:** No direct `DocumentSignature.query`, `UserNotification.query`, or `ExternalLink.query` for reads.

---

## Section 7: Roles and manager permissions (read-only)

**Goal:** Role lookups by name and manager permission reads use data_layer.

**Remaining in app.py (this section):**

| Location (approx) | Current code | Change to |
|-------------------|--------------|-----------|
| ~7924 | `Role.query.filter(db.func.lower(Role.name) == name.lower()).first()` | data_layer: `get_role_by_name(name)` (list_roles + find in Python, or add API by name). |
| ~7420 | `ManagerPermission.query.filter_by(user_id=u.id).all()` | data_layer: `list_manager_permissions(user_id)` (already exists). |

**Data API / data_layer:**  
- Optional: GET `/roles?name=...` or use existing list_roles and filter.  
- data_layer: `get_role_by_name(name)`.

**Done when:** No `Role.query` or `ManagerPermission.query` for reads (except in migration helpers that are already gated).

---

## Section 8: Checklist (NewHireChecklist) and typed fields (read-only)

**Goal:** New hire checklist completion and document typed fields are read via data_layer.

**Remaining in app.py (this section):**

| Location (approx) | Current code | Change to |
|-------------------|--------------|-----------|
| ~4058, 5457 | `NewHireChecklist.query.filter_by(new_hire_id=..., is_completed=True).count()` | data_layer: `count_new_hire_checklist_completed(new_hire_id)` or `list_new_hire_checklist(new_hire_id)` and count in Python; add API + data_layer. |
| ~10006 | `DocumentTypedField.query.filter_by(document_id=doc_id).all()` | data_layer: `list_document_typed_fields(document_id)`; add API + data_layer. |
| ~11361 | `DocumentTypedField.query.first()` (existence check) | data_layer: e.g. `list_document_typed_fields()` with limit 1 or has_typed_fields(). |
| ~11448 | `DocumentTypedField.query.get(field_id)` | data_layer: `get_document_typed_field(field_id)`; add API + data_layer. |

**Data API:**  
- GET `/new-hire-checklist?new_hire_id=...&is_completed=true` (or count endpoint).  
- GET `/document-typed-fields?document_id=...`, GET `/document-typed-fields/{field_id}`.

**api_client / data_layer:**  
- `list_new_hire_checklist(new_hire_id, is_completed=...)`, `count_new_hire_checklist_completed(new_hire_id)`.  
- `list_document_typed_fields(document_id)`, `get_document_typed_field(field_id)`.

**Done when:** No `NewHireChecklist.query` or `DocumentTypedField.query` / `DocumentTypedFieldValue.query` for reads.

---

## Section 9: UserTask and DocumentAssignment (remaining reads)

**Goal:** Any remaining read of UserTask or DocumentAssignment that isn’t already using data_layer goes through data_layer.

**Remaining in app.py (this section):**

| Location (approx) | Current code | Change to |
|-------------------|--------------|-----------|
| ~2443, 5274 | `UserTask.query.filter_by(...).first()` | data_layer: `list_user_tasks(username)` and find by task type/criteria, or add get-by-criteria endpoint. |
| ~11942 | `UserTask.query.filter_by(assignment_id=...)...` | data_layer: `list_user_tasks(...)` with filter by assignment if needed, or get_user_task by id. |

**Data API / data_layer:**  
- You already have get_user_task(id), list_user_tasks(username). Add filter by assignment_id if needed.

**Done when:** No remaining `UserTask.query` or `DocumentAssignment.query` for reads (except in migration helpers).

---

## Section 10: Migration / schema helpers (no DB when USE_DATA_API)

**Goal:** All `_ensure_*` and schema-check/ALTER blocks run only when **not** USE_DATA_API (or are no-ops when USE_DATA_API so the main app never touches the DB).

**Remaining:**  
- Audit every `db.session.execute(text(...))`, `db.session.commit()`, and ALTER TABLE / CREATE TABLE in app.py that are for migration/setup.  
- At the top of each such block: `if getattr(config, 'USE_DATA_API', False): return` (or skip the block).  
- Ensure no code path that runs with USE_DATA_API calls these helpers in a way that still hits the DB.

**Done when:** With USE_DATA_API=True, the main app never executes any migration/schema SQL.

---

## Section 11: Writes (db.session.add / commit / delete / update)

**Goal:** When USE_DATA_API, all creates/updates/deletes go through the Data API (no db.session in the main app).

**Scope:**  
- Every route that does `db.session.add`, `db.session.commit`, `db.session.delete`, or `Model.query.update` must either:  
  - call a Data API write endpoint (POST/PATCH/PUT/DELETE) when USE_DATA_API, or  
  - be disabled or show “not available in API mode” when USE_DATA_API.  
- Add write endpoints to data_api for: users, new_hires, stores, documents, document_stores, roles, manager_permissions, user_tasks, document_assignments, document_signature_fields, document_signatures, checklist items, new_hire_checklist, training progress, notifications, external links, typed fields, etc.

**Suggested order:**  
1. User and store writes (create/update/delete user, store).  
2. New hire and role writes.  
3. Document and document_stores writes.  
4. Assignments, tasks, signatures.  
5. Checklist and training progress.  
6. Notifications, external links, typed fields, admin settings.

**Done when:** With USE_DATA_API=True, the app runs without any db.session usage and all mutations go through the API.

---

## Quick reference: section order

| # | Section | Focus |
|---|---------|--------|
| 1 | New Hires list and dashboard | NewHire.query, required_training_videos, store filter, checklist count stub |
| 2 | Documents – manage + archived | Archived list/count, DocumentSignature by document_id |
| 3 | Documents – rest | Dashboard visible_documents, store forms, assignment docs, stats counts |
| 4 | Users and stores | UserModel.query.get, list by store/role, store counts |
| 5 | Training progress | UserTrainingProgress.query → list_user_training_progress |
| 6 | Signatures, notifications, external links | DocumentSignature, UserNotification, ExternalLink |
| 7 | Roles and manager permissions | Role by name, ManagerPermission (already have list) |
| 8 | Checklist and typed fields | NewHireChecklist, DocumentTypedField, DocumentTypedFieldValue |
| 9 | UserTask / DocumentAssignment | Remaining filter_by / list by assignment |
| 10 | Migration helpers | Gate all schema/ALTER so no DB when USE_DATA_API |
| 11 | Writes | All db.session.add/commit/delete/update via API |

Start with **Section 1** and proceed in order; each section can be tested with USE_DATA_API set before moving on.
