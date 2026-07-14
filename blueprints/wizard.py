"""Migrated wizard routes from app.py."""
from __future__ import annotations

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user

from auth import login_required
from document_wizard import (
    apply_wizard_field_skip,
    first_incomplete_required_wizard_index,
    wizard_progress_counts,
    wizard_required_steps_complete,
)
from models import Document, DocumentSignature, DocumentSignatureField, DocumentTypedField, db
from services.document_fields import (
    TYPED_FIELD_PHONE_REGEX_JS,
    document_fully_completed_for_user,
    normalize_last4_typed_value,
    validate_typed_field_value,
    _try_auto_import_acroform_fields,
)
from services.document_urls import (
    user_document_completed_view_url,
    user_sign_document_classic_url,
)
from services.documents_pdf import _document_is_fillable_pdf
from services.test_form import _test_form_field_is_last4, _test_form_last4_digits
from services.wizard import (
    _document_wizard_emp_acks_key,
    _document_wizard_emp_parts_key,
    _document_wizard_has_dependents_key,
    _document_wizard_index_key,
    _document_wizard_overlay_key,
    _document_wizard_user_defaults,
    _finalize_document_completion,
    _load_document_wizard_steps,
    _persist_signature_for_user,
    _user_can_fill_document,
    _wizard_persist_typed,
)


def register(app: Flask) -> None:
    """Register wizard routes (endpoint names unchanged)."""

    @app.route('/documents/<int:doc_id>/wizard/save-field', methods=['POST'])
    @login_required
    def document_wizard_save_field(doc_id):
        from flask import jsonify, get_flashed_messages

        wants_json = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or (request.form.get('xhr') or '') == '1'
        )

        def respond(endpoint_url, *, error=None, category='error'):
            if error:
                flash(error, category)
            if wants_json:
                flashes = [
                    {'category': c, 'message': m}
                    for c, m in get_flashed_messages(with_categories=True)
                ]
                return jsonify({
                    'ok': error is None,
                    'redirect': endpoint_url,
                    'error': error,
                    'flashes': flashes,
                })
            return respond(endpoint_url)

        document = Document.query.get(doc_id)
        if not document:
            flash('Document not found.', 'error')
            return respond(url_for('view_documents'))
        if not _user_can_fill_document(document, current_user.username):
            flash('This document has not been assigned to you.', 'error')
            return respond(url_for('view_documents'))

        wizard_id = (request.form.get('wizard_id') or '').strip()
        direction = (request.form.get('direction') or 'next').strip()
        value = (request.form.get('value') or '').strip()
        username = current_user.username

        steps, signature_fields, typed_fields = _load_document_wizard_steps(document, username)
        step_map = {s['wizard_id']: s for s in steps}
        if wizard_id not in step_map:
            flash('Invalid field.', 'error')
            return respond(url_for('view_documents', wizard=doc_id))

        step = step_map[wizard_id]
        idx = next((i for i, s in enumerate(steps) if s['wizard_id'] == wizard_id), 0)

        try:
            if direction == 'skip':
                if step.get('required'):
                    flash('This field is required.', 'error')
                    session[_document_wizard_index_key(doc_id)] = idx
                    return respond(url_for('view_documents', wizard=doc_id))

                if step.get('kind') == 'overlay':
                    overlay_key = step.get('overlay_key') or ''
                    overlays = dict(session.get(_document_wizard_overlay_key(doc_id)) or {})
                    overlays[overlay_key] = step.get('skip_value') or ''
                    session[_document_wizard_overlay_key(doc_id)] = overlays
                elif step.get('kind') == 'emp_part':
                    pk = step.get('part_key') or ''
                    role = step.get('part_role') or ''
                    parts = dict(session.get(_document_wizard_emp_parts_key(doc_id)) or {})
                    if pk and role:
                        parts[f'{pk}:{role}'] = step.get('skip_value') or ''
                        session[_document_wizard_emp_parts_key(doc_id)] = parts
                elif step.get('kind') == 'gate' and step.get('emp_composite'):
                    pk = step.get('part_key') or ''
                    role = step.get('part_role') or ''
                    parts = dict(session.get(_document_wizard_emp_parts_key(doc_id)) or {})
                    if pk and role:
                        parts[f'{pk}:{role}'] = ''
                        session[_document_wizard_emp_parts_key(doc_id)] = parts
                else:
                    def _persist_skipped_field(field_id, value):
                        tf = DocumentTypedField.query.get(field_id)
                        if tf and tf.document_id == doc_id:
                            _wizard_persist_typed(doc_id, tf, value, username)

                    apply_wizard_field_skip(step, _persist_skipped_field)
                db.session.commit()
                _finalize_document_completion(doc_id, username)
            elif direction != 'back':
                if step['kind'] == 'info':
                    acks = dict(session.get(_document_wizard_emp_acks_key(doc_id)) or {})
                    acks[wizard_id] = '1'
                    session[_document_wizard_emp_acks_key(doc_id)] = acks
                elif step['kind'] == 'gate':
                    if step.get('employer_count_gate'):
                        from employment_pdf_field_map import EMP_EMPLOYER_BLOCKS
                        ans = value.strip()
                        max_jobs = len(EMP_EMPLOYER_BLOCKS)
                        if not ans.isdigit() or not (1 <= int(ans) <= max_jobs):
                            flash(f'Please select how many jobs to enter (1–{max_jobs}).', 'error')
                            session[_document_wizard_index_key(doc_id)] = idx
                            return respond(url_for('view_documents', wizard=doc_id))
                        new_count = int(ans)
                        parts = dict(session.get(_document_wizard_emp_parts_key(doc_id)) or {})
                        gate_key = f"{step.get('part_key') or ''}:{step.get('part_role') or ''}"
                        prev_raw = (parts.get(gate_key) or '').strip()
                        prev_count = int(prev_raw) if prev_raw.isdigit() else None
                        parts[gate_key] = ans
                        session[_document_wizard_emp_parts_key(doc_id)] = parts
                        from employment_wizard_labels import (
                            clear_employer_block_values,
                            clear_employers_beyond_count,
                            emp_id_by_acro,
                            persist_employment_composites_to_db,
                            save_employment_wizard_parts,
                            sync_employment_date_overlays,
                        )
                        id_by_acro = emp_id_by_acro(typed_fields)

                        def _persist_employer_count_field(field_id, field_val):
                            tf = DocumentTypedField.query.get(field_id)
                            if tf and tf.document_id == doc_id:
                                _wizard_persist_typed(doc_id, tf, field_val, username)

                        if prev_count is not None and new_count > prev_count:
                            for block in EMP_EMPLOYER_BLOCKS[prev_count:new_count]:
                                clear_employer_block_values(
                                    block, parts, _persist_employer_count_field, id_by_acro,
                                )
                            session[_document_wizard_emp_parts_key(doc_id)] = parts
                        clear_employers_beyond_count(
                            new_count, parts, _persist_employer_count_field, id_by_acro,
                        )
                        session[_document_wizard_emp_parts_key(doc_id)] = parts
                        persist_employment_composites_to_db(
                            doc_id, typed_fields, parts, username, _wizard_persist_typed,
                        )
                        sync_employment_date_overlays(session, doc_id, parts)
                        save_employment_wizard_parts(doc_id, username, parts)
                    else:
                        ans = value.strip().lower()
                        if ans not in ('yes', 'no'):
                            flash('Please select Yes or No.', 'error')
                            session[_document_wizard_index_key(doc_id)] = idx
                            return respond(url_for('view_documents', wizard=doc_id))
                        if step.get('edu_section_gate'):
                            parts = dict(session.get(_document_wizard_emp_parts_key(doc_id)) or {})
                            pk = step.get('part_key') or ''
                            role = step.get('part_role') or ''
                            prev = (parts.get(f'{pk}:{role}') or '').strip().lower() if pk and role else ''
                            if pk and role:
                                parts[f'{pk}:{role}'] = ans
                                session[_document_wizard_emp_parts_key(doc_id)] = parts
                            from employment_wizard_labels import (
                                apply_education_section_not_applicable,
                                clear_education_section_values,
                                emp_id_by_acro,
                                persist_employment_composites_to_db,
                                save_employment_wizard_parts,
                                sync_education_name_overlays,
                                sync_employment_date_overlays,
                            )
                            id_by_acro = emp_id_by_acro(typed_fields)

                            def _persist_edu_gate_field(field_id, field_val):
                                tf = DocumentTypedField.query.get(field_id)
                                if tf and tf.document_id == doc_id:
                                    _wizard_persist_typed(doc_id, tf, field_val, username)

                            if ans == 'no' and pk:
                                apply_education_section_not_applicable(
                                    pk, typed_fields, parts, _persist_edu_gate_field, id_by_acro,
                                )
                                session[_document_wizard_emp_parts_key(doc_id)] = parts
                                persist_employment_composites_to_db(
                                    doc_id, typed_fields, parts, username, _wizard_persist_typed,
                                )
                            elif prev == 'no' and ans == 'yes' and pk:
                                clear_education_section_values(
                                    pk, typed_fields, parts, _persist_edu_gate_field, id_by_acro,
                                )
                                session[_document_wizard_emp_parts_key(doc_id)] = parts
                            save_employment_wizard_parts(doc_id, username, parts)
                        elif step.get('emp_composite'):
                            parts = dict(session.get(_document_wizard_emp_parts_key(doc_id)) or {})
                            pk = step.get('part_key') or ''
                            role = step.get('part_role') or ''
                            if pk and role:
                                parts[f'{pk}:{role}'] = ans
                                session[_document_wizard_emp_parts_key(doc_id)] = parts
                                from employment_wizard_labels import (
                                    persist_employment_composites_to_db,
                                    sync_education_name_overlays,
                                    sync_employment_date_overlays,
                                )
                                persist_employment_composites_to_db(
                                    doc_id, typed_fields, parts, username, _wizard_persist_typed,
                                )
                                sync_employment_date_overlays(session, doc_id, parts)
                                sync_education_name_overlays(session, doc_id, parts)
                        else:
                            deps_key = _document_wizard_has_dependents_key(doc_id)
                            prev = session.get(deps_key)
                            session[deps_key] = ans
                            from document_wizard_labels import (
                                apply_ee_dependents_not_applicable,
                                clear_ee_dependents_values,
                                ee_id_by_acro,
                            )
                            id_by_acro = ee_id_by_acro(typed_fields)

                            def _persist_gate_field(field_id, field_val):
                                tf = DocumentTypedField.query.get(field_id)
                                if tf and tf.document_id == doc_id:
                                    _wizard_persist_typed(doc_id, tf, field_val, username)

                            if ans == 'no':
                                apply_ee_dependents_not_applicable(_persist_gate_field, id_by_acro)
                            elif prev == 'no':
                                clear_ee_dependents_values(_persist_gate_field, id_by_acro)
                elif step['kind'] == 'overlay':
                    overlay_key = step.get('overlay_key') or ''
                    overlays = dict(session.get(_document_wizard_overlay_key(doc_id)) or {})
                    if direction == 'skip':
                        overlays[overlay_key] = step.get('skip_value') or ''
                    else:
                        overlays[overlay_key] = value
                    session[_document_wizard_overlay_key(doc_id)] = overlays
                elif step['kind'] == 'emp_part':
                    pk = step.get('part_key') or ''
                    role = step.get('part_role') or ''
                    parts = dict(session.get(_document_wizard_emp_parts_key(doc_id)) or {})
                    if pk and role:
                        if direction == 'skip':
                            parts[f'{pk}:{role}'] = step.get('skip_value') or ''
                        else:
                            parts[f'{pk}:{role}'] = value
                        session[_document_wizard_emp_parts_key(doc_id)] = parts
                        from employment_wizard_labels import (
                            persist_employment_composites_to_db,
                            sync_education_name_overlays,
                            sync_employment_date_overlays,
                        )
                        persist_employment_composites_to_db(
                            doc_id, typed_fields, parts, username, _wizard_persist_typed,
                        )
                        sync_employment_date_overlays(session, doc_id, parts)
                        sync_education_name_overlays(session, doc_id, parts)
                elif step['kind'] == 'ack_group':
                    if direction != 'skip':
                        checked_raw = request.form.getlist('ack_field')
                        checked_ids = set()
                        for raw in checked_raw:
                            try:
                                checked_ids.add(int(raw))
                            except (TypeError, ValueError):
                                pass
                        missing = [
                            opt['label']
                            for opt in (step.get('options') or [])
                            if opt.get('required') and opt.get('field_id') not in checked_ids
                        ]
                        if missing:
                            flash(
                                'Please check all required acknowledgements: '
                                + ', '.join(missing[:3])
                                + ('…' if len(missing) > 3 else ''),
                                'error',
                            )
                            session[_document_wizard_index_key(doc_id)] = idx
                            return respond(url_for('view_documents', wizard=doc_id))
                        for opt in step.get('options') or []:
                            fid = opt['field_id']
                            tf = DocumentTypedField.query.get(fid)
                            if not tf or tf.document_id != doc_id:
                                continue
                            field_value = 'X' if fid in checked_ids else ''
                            _wizard_persist_typed(doc_id, tf, field_value, username)
                elif step['kind'] == 'choice_group':
                    if direction != 'skip':
                        if not value:
                            flash('Please select one option.', 'error')
                            session[_document_wizard_index_key(doc_id)] = idx
                            return respond(url_for('view_documents', wizard=doc_id))
                        selected_id = int(value)
                        for opt in step.get('options') or []:
                            fid = opt['field_id']
                            tf = DocumentTypedField.query.get(fid)
                            if not tf or tf.document_id != doc_id:
                                continue
                            if fid == selected_id:
                                ok, err = validate_typed_field_value('checkbox_choice', 'X', tf.field_label)
                                if not ok:
                                    flash(err, 'error')
                                    session[_document_wizard_index_key(doc_id)] = idx
                                    return respond(url_for('view_documents', wizard=doc_id))
                                _wizard_persist_typed(doc_id, tf, 'X', username)
                            else:
                                _wizard_persist_typed(doc_id, tf, '', username)
                        selected_acro = None
                        for opt in step.get('options') or []:
                            if opt['field_id'] == selected_id:
                                selected_acro = opt.get('acro')
                                break
                        followups = step.get('followups') or []
                        active_fu = next(
                            (fu for fu in followups if fu.get('trigger_acro') == selected_acro),
                            None,
                        )
                        if not active_fu:
                            active_fu = next(
                                (
                                    fu for fu in followups
                                    if fu.get('trigger_yes') and selected_acro in (fu.get('yes_acros') or [])
                                ),
                                None,
                            )
                        for fu in followups:
                            if active_fu and fu.get('field_id') == active_fu.get('field_id'):
                                continue
                            tf_clear = DocumentTypedField.query.get(fu.get('field_id'))
                            if tf_clear and tf_clear.document_id == doc_id:
                                _wizard_persist_typed(doc_id, tf_clear, '', username)
                        if active_fu:
                            followup_val = (request.form.get('followup_value') or '').strip()
                            if active_fu.get('required') and not followup_val:
                                flash(
                                    f'Please provide: {active_fu.get("label", "details")}.',
                                    'error',
                                )
                                session[_document_wizard_index_key(doc_id)] = idx
                                return respond(url_for('view_documents', wizard=doc_id))
                            tf_fu = DocumentTypedField.query.get(active_fu.get('field_id'))
                            if tf_fu and tf_fu.document_id == doc_id:
                                if followup_val:
                                    ok, err = validate_typed_field_value(
                                        tf_fu.field_type,
                                        followup_val,
                                        tf_fu.field_label,
                                        placeholder=tf_fu.placeholder,
                                        wizard_type=active_fu.get('wizard_type'),
                                    )
                                    if not ok:
                                        flash(err, 'error')
                                        session[_document_wizard_index_key(doc_id)] = idx
                                        return respond(url_for('view_documents', wizard=doc_id))
                                    _wizard_persist_typed(doc_id, tf_fu, followup_val, username)
                                else:
                                    _wizard_persist_typed(doc_id, tf_fu, '', username)
                elif step['kind'] == 'signature':
                    if direction != 'skip':
                        if not request.form.get('consent'):
                            flash('Please confirm you agree to apply your electronic signature.', 'error')
                            session[_document_wizard_index_key(doc_id)] = idx
                            return respond(url_for('view_documents', wizard=doc_id))
                        if not value:
                            flash('Please draw your signature.', 'error')
                            session[_document_wizard_index_key(doc_id)] = idx
                            return respond(url_for('view_documents', wizard=doc_id))
                        sig_field = DocumentSignatureField.query.get(step['db_id'])
                        if not sig_field or sig_field.document_id != doc_id:
                            flash('Invalid signature field.', 'error')
                            return respond(url_for('view_documents', wizard=doc_id))
                        _persist_signature_for_user(doc_id, sig_field, value, username, consent_given=True)
                elif step['kind'] == 'typed':
                    from employment_wizard_labels import _employment_yesno_persist_value
                    tf = DocumentTypedField.query.get(step['db_id'])
                    if not tf or tf.document_id != doc_id:
                        flash('Invalid field.', 'error')
                        return respond(url_for('view_documents', wizard=doc_id))
                    if direction != 'skip':
                        if step.get('wizard_type') == 'yes_no':
                            ans = value.strip().lower()
                            if ans not in ('yes', 'no'):
                                flash('Please select Yes or No.', 'error')
                                session[_document_wizard_index_key(doc_id)] = idx
                                return respond(url_for('view_documents', wizard=doc_id))
                            field_value = _employment_yesno_persist_value(ans)
                        elif tf.field_type == 'checkbox_choice':
                            field_value = 'X' if value == 'X' else ''
                        elif tf.field_type == 'last4':
                            field_value = normalize_last4_typed_value(value)
                        else:
                            field_value = value
                            if not field_value and tf.field_type in ('typed_name', 'typed_initials', 'date'):
                                _, _, today = _document_wizard_user_defaults(username)
                                if tf.field_type == 'typed_name':
                                    field_value = _document_wizard_user_defaults(username)[0]
                                elif tf.field_type == 'typed_initials':
                                    field_value = _document_wizard_user_defaults(username)[1]
                                else:
                                    field_value = today
                        if step.get('required') and not field_value and direction != 'skip':
                            flash('This field is required.', 'error')
                            session[_document_wizard_index_key(doc_id)] = idx
                            return respond(url_for('view_documents', wizard=doc_id))
                        if field_value:
                            ok, err = validate_typed_field_value(
                                tf.field_type,
                                field_value,
                                tf.field_label,
                                placeholder=tf.placeholder,
                                wizard_type=step.get('wizard_type'),
                            )
                            if not ok:
                                flash(err, 'error')
                                session[_document_wizard_index_key(doc_id)] = idx
                                return respond(url_for('view_documents', wizard=doc_id))
                            _wizard_persist_typed(doc_id, tf, field_value, username)
                        elif tf.field_type == 'checkbox_choice':
                            _wizard_persist_typed(doc_id, tf, '', username)

                db.session.commit()
                _finalize_document_completion(doc_id, username)

            if direction == 'back':
                session[_document_wizard_index_key(doc_id)] = max(0, idx - 1)
            elif direction == 'skip' or direction == 'next':
                steps_next, _, _ = _load_document_wizard_steps(document, username)
                cur_idx = next(
                    (i for i, s in enumerate(steps_next) if s['wizard_id'] == wizard_id),
                    idx,
                )
                if cur_idx + 1 >= len(steps_next):
                    if wizard_required_steps_complete(steps_next):
                        session.pop(_document_wizard_index_key(doc_id), None)
                        return respond(url_for('view_documents', wizard=doc_id, done=1))
                    miss_idx = first_incomplete_required_wizard_index(steps_next)
                    miss = steps_next[miss_idx]
                    flash(f'Please complete: {miss.get("label", "required field")}', 'error')
                    session[_document_wizard_index_key(doc_id)] = miss_idx
                else:
                    session[_document_wizard_index_key(doc_id)] = cur_idx + 1
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.exception('document_wizard_save_field failed')
            flash(f'Could not save: {e}', 'error')
            session[_document_wizard_index_key(doc_id)] = idx

        return respond(url_for('view_documents', wizard=doc_id))



    @app.route('/documents/<int:doc_id>/wizard')
    @login_required
    def document_wizard_redirect(doc_id):
        """Friendly URL → query-param wizard (IIS-safe)."""
        return redirect(url_for('view_documents', wizard=doc_id))

    def _serve_document_wizard_page(doc_id):
        """Step-by-step mobile-friendly form for assigned documents with many fields."""
        try:
            document = Document.query.get(doc_id)
            if not document:
                flash('Document not found.', 'error')
                return redirect(url_for('view_documents'))
            if not _user_can_fill_document(document, current_user.username):
                flash('This document has not been assigned to you.', 'error')
                return redirect(url_for('view_documents'))

            if _document_is_fillable_pdf(document):
                _try_auto_import_acroform_fields(document, current_user.username)

            steps, _, _ = _load_document_wizard_steps(document, current_user.username)
            if not steps:
                flash(
                    'This document does not have any fields configured yet. '
                    'Ask an administrator to import fields from the PDF.',
                    'error',
                )
                return redirect(url_for('view_documents'))

            if request.args.get('done') == '1':
                done_count, total_count = wizard_progress_counts(steps)
                complete = document_fully_completed_for_user(doc_id, current_user.username)
                return render_template('wizard/complete.html', document=document,
                    doc_id=doc_id,
                    done_count=done_count,
                    total_count=total_count,
                    complete=complete, user_document_completed_view_url=user_document_completed_view_url, user_sign_document_classic_url=user_sign_document_classic_url)

            idx = session.get(_document_wizard_index_key(doc_id))
            if request.args.get('restart') == '1':
                session.pop(_document_wizard_has_dependents_key(doc_id), None)
                session.pop(_document_wizard_emp_acks_key(doc_id), None)
                session.pop(_document_wizard_overlay_key(doc_id), None)
                session.pop(_document_wizard_emp_parts_key(doc_id), None)
            if idx is None or request.args.get('restart') == '1':
                idx = first_incomplete_required_wizard_index(steps)
            else:
                idx = max(0, min(int(idx), len(steps) - 1))
            session[_document_wizard_index_key(doc_id)] = idx

            field = steps[idx]
            current_val = field.get('value') or ''
            is_last4 = field.get('wizard_type') == 'last4' or _test_form_field_is_last4({
                'type': field.get('wizard_type') or field.get('field_type') or '',
                'label': field.get('label', ''),
            })
            is_phone = field.get('wizard_type') == 'phone'
            last4_digits = _test_form_last4_digits(current_val) if is_last4 else ''
            is_signature = field.get('wizard_type') == 'signature'
            sig_b64_existing = ''
            if is_signature and current_user.username:
                try:
                    sig_row = DocumentSignature.query.filter_by(
                        document_id=doc_id,
                        signature_field_id=field.get('db_id'),
                        username=current_user.username,
                    ).first()
                    if sig_row and sig_row.signature_image:
                        sig_b64_existing = sig_row.signature_image
                except Exception:
                    pass

            done_count, total_count = wizard_progress_counts(steps)
            progress_pct = int(100 * done_count / max(total_count, 1))

            return render_template('wizard/step.html', document=document,
                doc_id=doc_id,
                field=field,
                idx=idx,
                total_count=total_count,
                done_count=done_count,
                progress_pct=progress_pct,
                current_val=current_val,
                is_last4=is_last4,
                is_phone=is_phone,
                last4_digits=last4_digits,
                typed_field_phone_regex_js=TYPED_FIELD_PHONE_REGEX_JS,
                is_signature=is_signature,
                sig_b64_existing=sig_b64_existing, user_document_completed_view_url=user_document_completed_view_url, user_sign_document_classic_url=user_sign_document_classic_url)
        except Exception as e:
            app.logger.exception('document wizard page failed doc_id=%s', doc_id)
            flash(f'Could not open form: {e}', 'error')
            return redirect(url_for('view_documents'))

    # Exposed for documents blueprint classic→wizard redirect.
    import app as main
    main._serve_document_wizard_page = _serve_document_wizard_page
