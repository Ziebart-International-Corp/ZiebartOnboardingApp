"""Rename EE PDF fields and sync document 14 DB rows to canonical names + new geometry."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from ee_pdf_field_map import canonical_acro
from rename_ee_pdf_fields import rename_pdf_fields

DOC_ID = 14


def sync_document_fields(doc_id: int = DOC_ID, pdf_path: Path | None = None) -> None:
    from app import app, db, _document_pdf_path
    from models import Document, DocumentTypedField, DocumentSignatureField
    from pdf_form_wizard import ACRO_PLACEHOLDER_PREFIX, collect_acroform_import_specs
    from document_wizard_labels import repair_employee_information_field_groups

    with app.app_context():
        document = Document.query.get(doc_id)
        if not document:
            raise SystemExit(f'Document {doc_id} not found')

        path = pdf_path or Path(_document_pdf_path(document) or '')
        if not path.is_file():
            raise SystemExit(f'PDF not found: {path}')

        count, lines = rename_pdf_fields(path)
        print(f'Renamed {count} PDF widget(s)')
        for line in lines:
            print(' ', line)

        specs = collect_acroform_import_specs(str(path))
        if not specs.get('ok'):
            raise SystemExit(specs.get('error', 'import failed'))

        # Migrate existing typed field placeholders legacy -> canonical
        typed_fields = DocumentTypedField.query.filter_by(document_id=doc_id).all()
        for tf in typed_fields:
            ak = canonical_acro((tf.placeholder or '').replace(ACRO_PLACEHOLDER_PREFIX, ''))
            new_ph = f'{ACRO_PLACEHOLDER_PREFIX}{ak}'
            if tf.placeholder != new_ph:
                print(f'  DB placeholder: {tf.placeholder} -> {new_ph}')
                tf.placeholder = new_ph

        by_acro: dict[str, DocumentTypedField] = {}
        for tf in typed_fields:
            ak = canonical_acro((tf.placeholder or '').replace(ACRO_PLACEHOLDER_PREFIX, ''))
            by_acro[ak] = tf

        for spec in specs.get('typed_fields') or []:
            wname = canonical_acro((spec.get('placeholder') or '').replace(ACRO_PLACEHOLDER_PREFIX, ''))
            ph = f'{ACRO_PLACEHOLDER_PREFIX}{wname}'
            tf = by_acro.get(wname)
            if tf:
                tf.page_number = spec['page_number']
                tf.x_position = spec['x_position']
                tf.y_position = spec['y_position']
                tf.width = spec['width']
                tf.height = spec['height']
                tf.field_type = spec['field_type']
                tf.choice_group = spec.get('choice_group')
                if spec.get('field_label'):
                    tf.field_label = spec['field_label'][:200]
                tf.placeholder = ph
            else:
                print(f'  Adding new field: {wname}')
                tf = DocumentTypedField(
                    document_id=doc_id,
                    page_number=spec['page_number'],
                    x_position=spec['x_position'],
                    y_position=spec['y_position'],
                    width=spec['width'],
                    height=spec['height'],
                    field_label=spec['field_label'],
                    field_type=spec['field_type'],
                    choice_group=spec.get('choice_group'),
                    placeholder=ph,
                    is_required=False if spec['field_type'] == 'checkbox_choice' else True,
                    created_by='sync_ee_fields',
                )
                db.session.add(tf)
                by_acro[wname] = tf

        sig_fields = DocumentSignatureField.query.filter_by(document_id=doc_id).order_by(
            DocumentSignatureField.id
        ).all()
        sig_specs = specs.get('signature_fields') or []
        for i, spec in enumerate(sig_specs):
            if i < len(sig_fields):
                sf = sig_fields[i]
                sf.page_number = spec['page_number']
                sf.x_position = spec['x_position']
                sf.y_position = spec['y_position']
                sf.width = spec['width']
                sf.height = spec['height']
                sf.field_label = spec['field_label']

        db.session.flush()
        all_typed = DocumentTypedField.query.filter_by(document_id=doc_id).all()
        if repair_employee_information_field_groups(all_typed):
            print('  Repaired choice_group assignments')

        document.original_filename = path.name
        db.session.commit()
        print(f'Synced document {doc_id}: {len(all_typed)} typed fields, {len(sig_fields)} signature fields')


if __name__ == '__main__':
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    sync_document_fields(pdf_path=pdf)
