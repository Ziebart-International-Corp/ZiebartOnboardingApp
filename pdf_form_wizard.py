"""
PDF test form wizard: extract fields from uploaded PDFs and guide one-at-a-time filling.
Uses PyMuPDF widgets when present; layout/text parsing for flat PDFs; optional OpenAI vision.
"""
from __future__ import annotations

import base64
import json
import os
import re
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False


def _openai_api_key() -> str:
    return (os.getenv('OPENAI_API_KEY') or '').strip()


def _openai_model() -> str:
    return (os.getenv('OPENAI_FORM_MODEL') or 'gpt-4o-mini').strip()


def _openai_max_pages() -> int:
    return int(os.getenv('OPENAI_FORM_MAX_PAGES') or '8')


FIELD_TYPES = frozenset({
    'text', 'textarea', 'date', 'number', 'phone', 'email',
    'checkbox', 'choice', 'signature', 'last4',
})

_SSN_LABEL_RE = re.compile(
    r'\b(social\s*security|ssn|tax\s*id\s*number|tax\s*id)\b',
    re.I,
)

WIDGET_TYPE_MAP = {
    1: 'text',
    2: 'checkbox',
    3: 'choice',
    4: 'choice',
    5: 'choice',
    6: 'signature',
}

# Section titles and boilerplate — not fill-in fields
_SKIP_LINE_EXACT = frozenset({
    'employee information', 'dependent information', 'acknowledgements',
    'medical information', 'in case of emergency', 'eeoc identification',
    'gender, race and ethnic group', 'list address if dependent is not living with you',
})

_LABEL_WORD_HINTS = re.compile(
    r'\b(name|date|number|address|email|phone|birthdate|birth\s*date|ssn|tax\s*id|'
    r'signature|relationship|contact|carrier|policy|gender|status|employee|hire|'
    r'medicare|medicaid|tobacco|dependent|initials|title|city|state|zip)\b',
    re.I,
)

_UNDERSCORE_SPLIT = re.compile(r'_{2,}')
_CHECKBOX_OPTION = re.compile(
    r'_{2,}\s*([A-Za-z][A-Za-z0-9\s\-\/\.]{0,40}?)(?=\s+_{2,}|\s*$)',
)


TEST_FORM_SIG_PREFIX = 'sigpng:'


def is_test_form_signature_value(value: str) -> bool:
    return (value or '').strip().startswith(TEST_FORM_SIG_PREFIX)


def test_form_signature_b64(value: str) -> str:
    val = (value or '').strip()
    if val.startswith(TEST_FORM_SIG_PREFIX):
        return val[len(TEST_FORM_SIG_PREFIX):]
    if val.startswith('data:image') and ',' in val:
        return val.split(',', 1)[1]
    return val


def normalize_test_form_signature_value(value: str) -> str:
    val = (value or '').strip()
    if not val:
        return ''
    if val.startswith(TEST_FORM_SIG_PREFIX):
        return val
    if val.startswith('data:image') and ',' in val:
        return TEST_FORM_SIG_PREFIX + val.split(',', 1)[1]
    if len(val) > 80 and re.fullmatch(r'[A-Za-z0-9+/=\s]+', val):
        return TEST_FORM_SIG_PREFIX + val.replace('\n', '').replace(' ', '')
    return ''


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_session_id() -> str:
    return uuid.uuid4().hex


def test_forms_dir(upload_root: Path) -> Path:
    d = upload_root / 'test_forms'
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_file_path(upload_root: Path, session_id: str) -> Path:
    return test_forms_dir(upload_root) / session_id / 'state.json'


def load_wizard_state(upload_root: Path, session_id: str) -> dict | None:
    path = state_file_path(upload_root, session_id)
    if not path.is_file():
        return None
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_wizard_state(upload_root: Path, state: dict) -> None:
    sid = state.get('session_id')
    if not sid:
        raise ValueError('state missing session_id')
    path = state_file_path(upload_root, sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)


def delete_wizard_state(upload_root: Path, session_id: str) -> None:
    folder = test_forms_dir(upload_root) / session_id
    if folder.is_dir():
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def save_uploaded_pdf(upload_root: Path, file_storage, session_id: str) -> tuple[str, str]:
    from werkzeug.utils import secure_filename

    original = secure_filename(file_storage.filename or 'form.pdf') or 'form.pdf'
    if not original.lower().endswith('.pdf'):
        original += '.pdf'
    folder = test_forms_dir(upload_root) / session_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'source.pdf'
    file_storage.save(str(path))
    return str(path.resolve()), original


def _normalize_field(raw: dict, index: int) -> dict | None:
    label = (raw.get('label') or raw.get('name') or '').strip()
    if not label:
        return None
    ftype = (raw.get('type') or 'text').strip().lower()
    if ftype not in FIELD_TYPES:
        ftype = 'text'
    if ftype in ('text', 'number') and _SSN_LABEL_RE.search(label):
        ftype = 'last4'
    page = int(raw.get('page') or 1)
    if page < 1:
        page = 1
    options = raw.get('options') or []
    if isinstance(options, str):
        options = [o.strip() for o in options.split('|') if o.strip()]
    rect = raw.get('rect')
    if rect and len(rect) == 4:
        try:
            rect = [float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])]
        except (TypeError, ValueError):
            rect = None
    else:
        rect = None
    return {
        'id': raw.get('id') or f'field_{index}',
        'label': label[:200],
        'type': ftype,
        'page': page,
        'required': bool(raw.get('required', True)),
        'hint': (raw.get('hint') or raw.get('help') or '')[:500],
        'options': [str(o)[:120] for o in options[:20]],
        'rect': rect,
        'widget_name': (raw.get('widget_name') or '')[:120],
    }


def _dedupe_fields(fields: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for f in fields:
        key = (
            f.get('label', '').lower().strip(),
            f.get('page', 1),
            f.get('type', 'text'),
            tuple(f.get('options') or ()),
            f.get('widget_name', ''),
        )
        if key in seen:
            continue
        seen.add(key)
        f['id'] = f'field_{len(out)}'
        out.append(f)
    return out


def _rect_for_underscore_line(text: str, bbox: tuple) -> list[float]:
    """Blank is on the same line, to the right of the label."""
    x0, y0, x1, y1 = bbox
    left = _UNDERSCORE_SPLIT.split(text)[0]
    ratio = len(left) / max(len(text), 1)
    label_end = x0 + (x1 - x0) * min(max(ratio, 0.15) + 0.08, 0.55)
    return [float(label_end), float(y0 + 1), float(x1 - 2), float(y1 - 1)]


def _rect_below_label(
    bbox: tuple,
    lines_on_page: list[dict],
    line_idx: int,
    page_width: float,
) -> list[float]:
    """Two-column forms: place input in the blank below the label, same column."""
    x0, y0, x1, y1 = bbox
    next_top = None
    for j in range(line_idx + 1, len(lines_on_page)):
        nb = lines_on_page[j]['bbox']
        if nb[1] > y1 + 1 and nb[0] < x1 + 30 and nb[2] > x0 - 30:
            next_top = nb[1]
            break
    gap_bottom = next_top if next_top is not None else y1 + 28
    height = min(max(gap_bottom - y1 - 4, 14), 40)
    if x0 < page_width * 0.45:
        rx1 = min(max(x1, x0 + 200), page_width * 0.48)
    else:
        rx1 = min(max(x1, x0 + 160), page_width - 12)
    return [float(x0), float(y1 + 2), float(rx1), float(y1 + 2 + height)]


def _line_bbox_to_rect(
    bbox: tuple,
    page_height: float,
    input_height: float = 18.0,
) -> list[float]:
    """Legacy fallback — prefer _rect_below_label / _rect_for_underscore_line."""
    x0, y0, x1, y1 = bbox
    return [float(x0), float(y1), float(x1), float(y1 + input_height)]


def _should_skip_line(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 120:
        return True
    low = re.sub(r'\s+', ' ', t.lower()).strip()
    if low in _SKIP_LINE_EXACT:
        return True
    if low.startswith('i have ') or 'completed all' in low:
        return True
    if _UNDERSCORE_SPLIT.search(t):
        left = _UNDERSCORE_SPLIT.split(t)[0].strip(' :.-')
        if len(left) >= 2:
            return False
    if t.count('_') > len(t) * 0.4:
        return True
    if re.match(r'^[\W_]+$', t):
        return True
    return False


def _looks_like_label_line(text: str) -> bool:
    t = text.strip()
    if _should_skip_line(t):
        return False
    if '___' in t or _UNDERSCORE_SPLIT.search(t):
        return False
    if t.endswith('.') or t.endswith(','):
        return False
    if len(t) < 2 or len(t) > 50:
        return False
    if '(' in t and len(t) > 32:
        return False
    if _LABEL_WORD_HINTS.search(t):
        return True
    words = t.split()
    if 1 <= len(words) <= 6 and t[0].isupper():
        if any(w.lower() in ('yes', 'no', 'male', 'female', 'single', 'married') for w in words):
            return False
        return True
    return False


def _extract_checkbox_options(text: str) -> list[str]:
    opts = []
    for m in _CHECKBOX_OPTION.finditer(text):
        opt = m.group(1).strip()
        if opt and opt not in opts:
            opts.append(opt)
    return opts


def _pdf_full_text_lower(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    try:
        parts = []
        for page in doc:
            parts.append(page.get_text('text') or '')
        return '\n'.join(parts).lower()
    finally:
        doc.close()


def _field_label_in_pdf(label: str, pdf_text: str) -> bool:
    """Require most label words to appear in extracted PDF text (reduces AI hallucinations)."""
    words = [w.lower() for w in re.findall(r'[a-zA-Z]{3,}', label)]
    if not words:
        return False
    hits = sum(1 for w in words if w in pdf_text)
    return hits >= max(1, int(len(words) * 0.55))


def extract_fields_from_layout(pdf_path: str) -> list[dict]:
    """
    Parse PDF text layer: labels with underscores, checkbox rows, and standalone label lines.
    """
    if not FITZ_AVAILABLE:
        return []
    fields = []
    doc = fitz.open(pdf_path)
    try:
        for page_index in range(doc.page_count):
            page = doc[page_index]
            page_num = page_index + 1
            page_h = float(page.rect.height)
            page_w = float(page.rect.width)
            blocks = page.get_text('dict').get('blocks') or []

            lines_on_page = []
            for block in blocks:
                if block.get('type') != 0:
                    continue
                for line in block.get('lines') or []:
                    spans = line.get('spans') or []
                    text = ''.join(s.get('text', '') for s in spans).strip()
                    if not text:
                        continue
                    bbox = tuple(line.get('bbox') or (0, 0, 0, 0))
                    lines_on_page.append({'text': text, 'bbox': bbox})

            for line_idx, item in enumerate(lines_on_page):
                text = item['text']
                bbox = item['bbox']
                if _should_skip_line(text):
                    continue

                cb_opts = _extract_checkbox_options(text)
                if len(cb_opts) >= 2:
                    group_label = ''
                    before = _UNDERSCORE_SPLIT.split(text)[0].strip(' :.-')
                    if before and not before.startswith('_') and '___' not in before:
                        group_label = before
                    if not group_label and line_idx > 0:
                        for back in range(1, min(4, line_idx + 1)):
                            prev = lines_on_page[line_idx - back]['text']
                            if _extract_checkbox_options(prev):
                                continue
                            if _looks_like_label_line(prev) or (
                                len(prev.strip()) < 40 and not prev.strip().startswith('_')
                            ):
                                group_label = prev.strip()
                                break
                    label = group_label or text[:50].strip()
                    if label.startswith('_') or '___' in label:
                        label = 'Select one'
                    fields.append({
                        'label': label,
                        'type': 'choice',
                        'page': page_num,
                        'required': True,
                        'hint': 'Select one option',
                        'options': cb_opts,
                        'rect': _rect_below_label(bbox, lines_on_page, line_idx, page_w),
                        'widget_name': '',
                    })
                    continue

                if _UNDERSCORE_SPLIT.search(text):
                    left = _UNDERSCORE_SPLIT.split(text)[0].strip(' :.-')
                    if left and len(left) >= 2:
                        fields.append({
                            'label': left,
                            'type': 'text',
                            'page': page_num,
                            'required': True,
                            'hint': '',
                            'options': [],
                            'rect': _rect_for_underscore_line(text, bbox),
                            'widget_name': '',
                        })
                    continue

                if 'signature' in text.lower():
                    sig_rect = _rect_below_label(bbox, lines_on_page, line_idx, page_w)
                    sig_rect[3] = sig_rect[1] + 32
                    fields.append({
                        'label': text.strip(),
                        'type': 'signature',
                        'page': page_num,
                        'required': True,
                        'hint': '',
                        'options': [],
                        'rect': sig_rect,
                        'widget_name': '',
                    })
                    continue

                if _looks_like_label_line(text):
                    low = text.lower()
                    ftype = 'text'
                    if 'date' in low or 'birthdate' in low or 'hire date' in low:
                        ftype = 'date'
                    elif 'phone' in low:
                        ftype = 'phone'
                    elif 'email' in low:
                        ftype = 'email'
                    elif 'number' in low and 'phone' not in low and 'policy' not in low:
                        ftype = 'number'
                    fields.append({
                        'label': text.strip(),
                        'type': ftype,
                        'page': page_num,
                        'required': True,
                        'hint': '',
                        'options': [],
                        'rect': _rect_below_label(bbox, lines_on_page, line_idx, page_w),
                        'widget_name': '',
                    })
    finally:
        doc.close()

    normalized = []
    for i, raw in enumerate(fields):
        n = _normalize_field(raw, i)
        if n:
            normalized.append(n)
    return _collapse_choice_text_duplicates(_dedupe_fields(normalized))


def _place_text_in_rect(page, rect: list[float], text: str, fontsize: float = 9) -> None:
    if not rect or len(rect) != 4:
        return
    val = (text or '').strip()
    if not val:
        return
    box = fitz.Rect(rect[0], rect[1], rect[2], rect[3])
    if box.width < 8 or box.height < 6:
        return
    fs = min(fontsize, max(7, box.height * 0.55))
    try:
        page.insert_textbox(
            box,
            val[:500],
            fontsize=fs,
            fontname='helv',
            color=(0, 0, 0),
            align=fitz.TEXT_ALIGN_LEFT,
        )
    except Exception:
        page.insert_text((box.x0 + 2, box.y0 + fs + 1), val[:200], fontsize=fs, color=(0, 0, 0))


def _append_summary_pages(doc, fields: list[dict], values: dict) -> None:
    """Add readable Q&A pages so no answer is lost even if overlay positions are imperfect."""
    lines = ['Completed form — summary of your answers', '']
    for field in fields:
        fid = field['id']
        val = values.get(fid)
        if val is None or str(val).strip() == '':
            continue
        label = field.get('label', 'Field')
        if field.get('type') == 'signature' and is_test_form_signature_value(str(val)):
            lines.append(f'• {label} (page {field.get("page", 1)}): [signature on file]')
        elif field.get('type') == 'checkbox':
            lines.append(f'• {label}: {"Yes" if val else "No"}')
        elif field.get('type') == 'choice':
            lines.append(f'• {label}: {val}')
        else:
            lines.append(f'• {label}: {val}')
    if len(lines) <= 2:
        return
    page = doc.new_page(width=612, height=792)
    y = 50
    page.insert_text((50, y), lines[0], fontsize=14, color=(0, 0, 0))
    y += 28
    for line in lines[2:]:
        if y > 740:
            page = doc.new_page(width=612, height=792)
            y = 50
        page.insert_text((50, y), line[:120], fontsize=10, color=(0, 0, 0))
        y += 14


def _collapse_choice_text_duplicates(fields: list[dict]) -> list[dict]:
    """If a choice group and text field share the same label on a page, keep the choice."""
    choice_keys = {
        (f['label'].lower(), f['page'])
        for f in fields
        if f.get('type') == 'choice'
    }
    out = []
    for f in fields:
        if f.get('type') == 'text' and (f['label'].lower(), f['page']) in choice_keys:
            continue
        if f.get('label', '').startswith('_'):
            continue
        out.append(f)
    for i, f in enumerate(out):
        f['id'] = f'field_{i}'
    return out


def extract_fields_from_widgets(pdf_path: str) -> list[dict]:
    if not FITZ_AVAILABLE:
        return []
    fields = []
    doc = fitz.open(pdf_path)
    try:
        for page_index in range(doc.page_count):
            page = doc[page_index]
            for w in page.widgets() or []:
                label = (w.field_label or w.field_name or '').strip()
                if not label:
                    label = f'Field on page {page_index + 1}'
                ftype = WIDGET_TYPE_MAP.get(w.field_type, 'text')
                rect = list(w.rect) if w.rect else None
                options = []
                if ftype == 'choice':
                    try:
                        options = list(w.choice_values or [])
                    except Exception:
                        options = []
                fields.append({
                    'label': label,
                    'type': ftype,
                    'page': page_index + 1,
                    'required': bool(w.field_flags & 2) if hasattr(w, 'field_flags') else True,
                    'hint': '',
                    'options': options,
                    'rect': rect,
                    'widget_name': (w.field_name or '')[:120],
                })
    finally:
        doc.close()
    normalized = []
    for i, raw in enumerate(fields):
        n = _normalize_field(raw, i)
        if n:
            normalized.append(n)
    return _dedupe_fields(normalized)


def _openai_chat_json(messages: list[dict]) -> tuple[list | None, str | None]:
    api_key = _openai_api_key()
    if not api_key:
        return None, 'OPENAI_API_KEY is not set. Add it to .env to use AI field detection on scanned PDFs.'
    import urllib.error
    import urllib.request

    body = json.dumps({
        'model': _openai_model(),
        'messages': messages,
        'temperature': 0,
        'response_format': {'type': 'json_object'},
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.openai.com/v1/chat/completions',
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode('utf-8')
            err_json = json.loads(err_body)
            msg = err_json.get('error', {}).get('message', err_body)
        except Exception:
            msg = str(e)
        return None, f'OpenAI API error: {msg}'
    except Exception as e:
        return None, f'OpenAI request failed: {e}'

    try:
        content = payload['choices'][0]['message']['content']
        parsed = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return None, f'Could not parse AI response: {e}'

    if isinstance(parsed, dict):
        for key in ('fields', 'form_fields', 'items'):
            if isinstance(parsed.get(key), list):
                return parsed[key], None
    if isinstance(parsed, list):
        return parsed, None
    return None, 'AI returned an unexpected JSON shape.'


def extract_fields_with_ai(pdf_path: str, pdf_text: str) -> tuple[list[dict], str | None]:
    if not FITZ_AVAILABLE:
        return [], 'PyMuPDF is not installed.'
    doc = fitz.open(pdf_path)
    try:
        page_count = doc.page_count
        n_pages = min(page_count, _openai_max_pages())
        text_excerpt = pdf_text[:12000]
        content_parts = [
            {
                'type': 'text',
                'text': (
                    'You are extracting fill-in fields from a PDF form image.\n'
                    'CRITICAL RULES:\n'
                    '- Only include blanks, boxes, checkboxes, or signature lines that are VISUALLY on the provided pages.\n'
                    '- Each field label MUST be copied from visible text on the form (do not invent generic fields).\n'
                    '- If the form has no fill-in areas, return {"fields":[]}.\n'
                    '- Prefer the EXTRACTED TEXT below for exact label wording.\n\n'
                    f'EXTRACTED TEXT FROM PDF:\n{text_excerpt}\n\n'
                    'Return JSON only: {"fields":[{"label":"exact label from form","type":"text|textarea|date|number|phone|email|'
                    'checkbox|choice|signature","page":1,"required":true,"hint":"","options":[],"rect":[x0,y0,x1,y1]}]}\n'
                    'rect = PDF points (top-left origin). Order top-to-bottom.\n'
                    f'Pages provided: {n_pages} of {page_count}.'
                ),
            },
        ]
        for i in range(n_pages):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            img_b64 = base64.standard_b64encode(pix.tobytes('png')).decode('ascii')
            content_parts.append({
                'type': 'text',
                'text': f'--- Page {i + 1} ({int(page.rect.width)} x {int(page.rect.height)} pt) ---',
            })
            content_parts.append({
                'type': 'image_url',
                'image_url': {'url': f'data:image/png;base64,{img_b64}', 'detail': 'high'},
            })
    finally:
        doc.close()

    messages = [{'role': 'user', 'content': content_parts}]
    raw_list, err = _openai_chat_json(messages)
    if err:
        return [], err
    if not raw_list:
        return [], None

    normalized = []
    for i, raw in enumerate(raw_list):
        if not isinstance(raw, dict):
            continue
        n = _normalize_field(raw, i)
        if n and _field_label_in_pdf(n['label'], pdf_text):
            normalized.append(n)
    return _dedupe_fields(normalized), None


def analyze_pdf(pdf_path: str) -> dict[str, Any]:
    """
    Detect form fields. Returns dict with keys: fields, source, message, ai_used.
    source: widgets | layout | ai | none
    """
    pdf_text = _pdf_full_text_lower(pdf_path) if FITZ_AVAILABLE else ''

    widgets = extract_fields_from_widgets(pdf_path)
    if widgets:
        return {
            'fields': widgets,
            'source': 'widgets',
            'message': f'Found {len(widgets)} fillable PDF form field(s).',
            'ai_used': False,
        }

    layout_fields = extract_fields_from_layout(pdf_path)
    if len(layout_fields) >= 3:
        return {
            'fields': layout_fields,
            'source': 'layout',
            'message': f'Found {len(layout_fields)} fields from the PDF text (labels and blanks on the form).',
            'ai_used': False,
        }

    ai_fields, ai_err = [], None
    if _openai_api_key():
        ai_fields, ai_err = extract_fields_with_ai(pdf_path, pdf_text)

    if ai_fields:
        merged = _dedupe_fields(layout_fields + ai_fields)
        if len(merged) >= len(ai_fields):
            return {
                'fields': merged,
                'source': 'ai',
                'message': f'AI plus PDF text: {len(merged)} fields (AI-only suggestions were filtered).',
                'ai_used': True,
            }
        return {
            'fields': ai_fields,
            'source': 'ai',
            'message': f'AI detected {len(ai_fields)} fields (verified against PDF text).',
            'ai_used': True,
        }

    if layout_fields:
        return {
            'fields': layout_fields,
            'source': 'layout',
            'message': f'Found {len(layout_fields)} field(s) from PDF text.',
            'ai_used': False,
        }

    err = ai_err or (
        'No form fields could be detected. The PDF may be a scanned image with no readable text — '
        'try OCR or a fillable PDF export.'
    )
    return {'fields': [], 'source': 'none', 'message': err, 'ai_used': False}


def build_filled_pdf(source_path: str, fields: list[dict], values: dict) -> bytes:
    if not FITZ_AVAILABLE:
        raise RuntimeError('PyMuPDF not available')
    doc = fitz.open(source_path)
    try:
        widget_by_name = {}
        for page in doc:
            for w in page.widgets() or []:
                if w.field_name:
                    widget_by_name[w.field_name] = w

        for field in fields:
            fid = field['id']
            val = values.get(fid)
            if val is None or str(val).strip() == '':
                continue
            val_str = str(val).strip()
            if field.get('type') == 'signature' and is_test_form_signature_value(val_str):
                b64 = test_form_signature_b64(val_str)
                if not b64:
                    continue
                try:
                    img_bytes = base64.standard_b64decode(b64)
                except Exception:
                    continue
                page_num = int(field.get('page') or 1) - 1
                if page_num < 0 or page_num >= doc.page_count:
                    continue
                page = doc[page_num]
                rect = field.get('rect')
                if rect and len(rect) == 4:
                    x0, y0, x1, y1 = rect
                    target = fitz.Rect(x0, y0, x1, y1)
                else:
                    ph = page.rect.height
                    pw = page.rect.width
                    target = fitz.Rect(pw * 0.15, ph * 0.75, pw * 0.55, ph * 0.82)
                try:
                    page.insert_image(target, stream=img_bytes, keep_proportion=True)
                except Exception:
                    pass
                continue
            wname = field.get('widget_name') or ''
            if wname and wname in widget_by_name:
                w = widget_by_name[wname]
                if field.get('type') == 'checkbox':
                    w.field_value = 'Yes' if val_str.lower() in ('1', 'true', 'yes', 'x', 'on') else 'Off'
                else:
                    w.field_value = val_str
                w.update()
                continue
            rect = field.get('rect')
            page_num = int(field.get('page') or 1) - 1
            if page_num < 0 or page_num >= doc.page_count:
                continue
            page = doc[page_num]
            if field.get('type') == 'choice':
                display = f'X {val_str}' if val_str else ''
                _place_text_in_rect(page, rect, display, fontsize=9)
            elif rect and len(rect) == 4:
                _place_text_in_rect(page, rect, val_str, fontsize=9)

        _append_summary_pages(doc, fields, values)

        unplaced = [
            f for f in fields
            if values.get(f['id']) and str(values.get(f['id'])).strip()
            and f.get('type') != 'signature'
            and not (f.get('widget_name') and f['widget_name'] in widget_by_name)
            and not f.get('rect')
        ]
        if unplaced:
            page = doc[doc.page_count - 1]
            y = 50
            page.insert_text((40, y), 'Form responses (test wizard):', fontsize=10, color=(0, 0, 0))
            y += 16
            for field in unplaced:
                val_str = str(values.get(field['id'], '')).strip()
                line = f'{field.get("label", "")}: {val_str}'[:220]
                page.insert_text((40, y), line, fontsize=8, color=(0, 0, 0))
                y += 12

        out = BytesIO()
        doc.save(out, garbage=4, deflate=True)
        return out.getvalue()
    finally:
        doc.close()


# Browser viewer uses 800px height (see set_signature_fields / sign document PDF.js)
SIGN_VIEWER_HEIGHT = 800.0
ACRO_PLACEHOLDER_PREFIX = 'acro:'


def pdf_rect_to_viewer_coords(rect4, page_height: float) -> tuple[float, float, float, float]:
    """Map PDF point rect to x, y, width, height in sign-page viewer pixels."""
    scale = SIGN_VIEWER_HEIGHT / float(page_height)
    x0, y0, x1, y1 = (float(rect4[0]), float(rect4[1]), float(rect4[2]), float(rect4[3]))
    width = max((x1 - x0) * scale, 24.0)
    height = max((y1 - y0) * scale, 18.0)
    return x0 * scale, y0 * scale, width, height


def _acro_widget_dedupe_key(widget, page_index: int) -> str:
    """Unique per widget instance (radio siblings may share field_name)."""
    wname = (widget.field_name or '').strip()
    rect = widget.rect
    if rect:
        r = tuple(round(float(c), 1) for c in rect)
    else:
        r = (0.0, 0.0, 0.0, 0.0)
    xref = getattr(widget, 'xref', None)
    if wname:
        return f'{page_index}:{wname}:{r}'
    return f'{page_index}:xref:{xref or id(widget)}:{r}'


def count_pdf_acroform_widgets(pdf_path: str) -> int:
    if not FITZ_AVAILABLE:
        return 0
    seen: set[str] = set()
    doc = fitz.open(pdf_path)
    try:
        for page_index, page in enumerate(doc):
            for w in page.widgets() or []:
                wtype = getattr(w, 'field_type', None)
                if wtype in (0, None):
                    continue
                key = _acro_widget_dedupe_key(w, page_index)
                if key not in seen:
                    seen.add(key)
    finally:
        doc.close()
    return len(seen)


def _acro_choice_group(field_name: str) -> str | None:
    name = (field_name or '').strip()
    if not name:
        return None
    if '.' in name:
        return name.rsplit('.', 1)[0][:100]
    return name[:100]


def _widget_to_app_typed_field_type(widget, label: str) -> str:
    wtype = getattr(widget, 'field_type', 1)
    if wtype == 2 or wtype == 5:
        return 'checkbox_choice'
    if wtype == 6:
        return 'signature'
    rect = list(getattr(widget, 'rect', []) or [])
    if len(rect) == 4 and _is_acro_radio_marker(rect):
        return 'checkbox_choice'
    if wtype in (3, 4):
        return 'text'
    if _SSN_LABEL_RE.search(label):
        return 'last4'
    label_lower = label.lower()
    if any(k in label_lower for k in ('date', 'dob', 'birth date', 'hire date')):
        return 'date'
    if 'phone' in label_lower or 'tel' in label_lower:
        return 'phone'
    return 'text'


def _page_text_lines(page) -> list[dict]:
    lines = []
    for block in page.get_text('dict').get('blocks') or []:
        if block.get('type') != 0:
            continue
        for line in block.get('lines') or []:
            text = ''.join(s.get('text', '') for s in line.get('spans') or []).strip()
            if not text or text.count('_') > len(text) * 0.5:
                continue
            bbox = line.get('bbox') or (0, 0, 0, 0)
            lines.append({'text': text, 'bbox': bbox})
    return lines


def _label_left_of_rect(lines: list[dict], rect: list[float]) -> str | None:
    x0, y0, x1, y1 = rect
    cy = (y0 + y1) / 2
    best = None
    best_dist = 9999.0
    for ln in lines:
        bx0, by0, bx1, by1 = ln['bbox']
        if by1 < y0 - 18 or by0 > y1 + 18:
            continue
        if bx1 > x0 + 8:
            continue
        text = ln['text'].strip(' :.-')
        if len(text) < 2 or len(text) > 90:
            continue
        dist = x0 - bx1
        if 0 <= dist < best_dist:
            best_dist = dist
            best = text
    return best


def _label_above_rect(lines: list[dict], rect: list[float]) -> str | None:
    x0, y0, x1, y1 = rect
    best = None
    best_dy = 9999.0
    for ln in lines:
        bx0, by0, bx1, by1 = ln['bbox']
        if by1 > y0 + 4:
            continue
        if bx1 < x0 - 40 or bx0 > x1 + 40:
            continue
        dy = y0 - by1
        if 0 < dy < best_dy and dy < 45:
            best_dy = dy
            best = ln['text'].strip(' :.-')
    return best


def _humanize_acro_widget_name(name: str) -> str | None:
    n = (name or '').strip()
    if not n:
        return None
    low = n.lower()
    if 'signature' in low and 'signer' in low:
        return 'Signature'
    if ':signer:email' in low:
        return 'Email address'
    if ':signer:date' in low:
        return 'Date'
    if ':signer:fullname' in low:
        return None
    if n in ('undefined',) or n.startswith('Check Box'):
        return None
    if re.match(r'^Text\d+$', n, re.I):
        return None
    if n.startswith('Yes') or n.startswith('No'):
        return n.split('_')[0]
    return n.replace('_', ' ').strip() or None


def _is_acro_radio_marker(rect: list[float]) -> bool:
    w = float(rect[2]) - float(rect[0])
    h = float(rect[3]) - float(rect[1])
    return w <= 42 and h <= 22


def _acro_option_category(label: str) -> str:
    l = (label or '').strip().lower()
    if l in ('male', 'female'):
        return 'gender'
    if l in ('single', 'married'):
        return 'marital'
    if l in ('yes', 'no'):
        return 'yesno'
    if any(k in l for k in ('black', 'indian', 'asian', 'hawaiian', 'hispanic', 'white')):
        return 'race'
    if any(k in l for k in ('handbook', 'training', 'hepatitis', 'safety', 'urethane', 'medicare', 'tobacco')):
        return 'ack'
    return 'other'


_KNOWN_ACRO_OPTION_LABELS = frozenset({
    'single', 'married', 'male', 'female', 'yes', 'no',
    'black/african american', 'american indian', 'asian',
    'native hawaiian/pacific islanders', 'hispanic/spanish', 'white (caucasian',
    'employee handbook received', 'harassment training completed',
    'technical training received', 'hepatitis b vaccine declination',
    'safety data sheets/safety handbook reviewed',
    'urethane liner safety received (rhino technician only',
})


def _apply_ee_canonical_choice_groups(typed_fields: list) -> None:
    """Assign choice_group from ee_pdf_field_map when widget names are canonical EE fields."""
    try:
        from ee_pdf_field_map import EE_ACRO_TO_CHOICE_GROUP, EE_ACK_ACROS, canonical_acro
    except ImportError:
        return
    ack_set = frozenset(EE_ACK_ACROS)
    for spec in typed_fields:
        wname = canonical_acro((spec.get('placeholder') or '').replace(ACRO_PLACEHOLDER_PREFIX, ''))
        if wname in ack_set:
            spec['field_type'] = 'checkbox_choice'
            spec['choice_group'] = None
            continue
        group = EE_ACRO_TO_CHOICE_GROUP.get(wname)
        if group:
            spec['field_type'] = 'checkbox_choice'
            spec['choice_group'] = group


def _is_exclusive_choice_pair(labels: list[str]) -> bool:
    """True when labels are a mutually exclusive pair (not independent checkboxes)."""
    if len(labels) != 2:
        return False
    a, b = (l.strip().lower() for l in labels)
    return (
        {a, b} == {'single', 'married'}
        or {a, b} == {'male', 'female'}
        or {a, b} == {'yes', 'no'}
    )


def _split_mixed_option_clusters(cluster: list) -> list[list]:
    """Split a row cluster that accidentally merged gender, race, yes/no, acks, etc."""
    buckets: dict[str, list] = {}
    for item in cluster:
        cat = _acro_option_category(item.get('field_label') or '')
        buckets.setdefault(cat, []).append(item)
    out: list[list] = []
    for cat, items in buckets.items():
        if cat == 'ack':
            out.extend([[item] for item in items])
        elif len(items) >= 2:
            out.append(items)
        else:
            out.extend([[item] for item in items])
    return out if out else [cluster]


def _slug_group_name(label: str, page: int, suffix: str = '') -> str:
    base = re.sub(r'[^a-zA-Z0-9]+', '_', (label or 'choice').strip().lower()).strip('_')
    if not base:
        base = 'choice'
    key = f'{base}_p{page}'
    if suffix:
        key = f'{key}_{suffix}'
    return key[:100]


def _enrich_acroform_import_specs(pdf_path: str, signature_fields: list, typed_fields: list) -> None:
    """Improve labels and group radio/checkbox markers using PDF text context."""
    if not FITZ_AVAILABLE or not typed_fields:
        return

    doc = fitz.open(pdf_path)
    try:
        page_lines = {i: _page_text_lines(doc[i]) for i in range(doc.page_count)}
        page_heights = {i + 1: doc[i].rect.height for i in range(doc.page_count)}

        # Promote signature-named text widgets to signature fields.
        remaining_typed = []
        for spec in typed_fields:
            wname = (spec.get('placeholder') or '').replace(ACRO_PLACEHOLDER_PREFIX, '')
            label = (spec.get('field_label') or '').strip()
            if 'signature' in wname.lower() and 'signer' in wname.lower():
                signature_fields.append({
                    'page_number': spec['page_number'],
                    'x_position': spec['x_position'],
                    'y_position': spec['y_position'],
                    'width': max(spec.get('width') or 120, 120.0),
                    'height': max(spec.get('height') or 50, 50.0),
                    'field_label': 'Signature',
                    'is_required': True,
                })
                continue
            remaining_typed.append(spec)
        typed_fields[:] = remaining_typed

        # Resolve human labels for unnamed/generic fields.
        for spec in typed_fields:
            page_num = spec['page_number']
            page_h = page_heights.get(page_num, 792)
            wname = (spec.get('placeholder') or '').replace(ACRO_PLACEHOLDER_PREFIX, '')
            rect_pdf = None
            # Reconstruct approximate PDF rect from viewer coords
            scale = SIGN_VIEWER_HEIGHT / float(page_h)
            x = spec['x_position'] / scale
            y = spec['y_position'] / scale
            w = (spec.get('width') or 24) / scale
            h = (spec.get('height') or 18) / scale
            rect_pdf = [x, y, x + w, y + h]

            lines = page_lines.get(page_num - 1, [])
            human = _humanize_acro_widget_name(wname)
            keep_option_label = (spec.get('field_label') or '').strip().lower() in _KNOWN_ACRO_OPTION_LABELS
            if not keep_option_label:
                if not human or human.lower() in ('undefined', 'yes', 'no', 'male', 'female', 'single', 'married'):
                    left = _label_left_of_rect(lines, rect_pdf)
                    above = _label_above_rect(lines, rect_pdf)
                    if left and above and len(above) < len(left):
                        human = left
                    elif left:
                        human = left
                    elif above:
                        human = above
                if human and human.lower() not in ('undefined',):
                    spec['field_label'] = human[:200]
                elif spec.get('field_label', '').lower() in ('undefined', 'yes', 'no', ''):
                    if left := _label_left_of_rect(lines, rect_pdf):
                        spec['field_label'] = left[:200]

            if wname and ':signer:date' in wname.lower() or (spec.get('field_label') or '').lower() == 'date':
                spec['field_type'] = 'date'
            if wname and ':signer:email' in wname.lower():
                spec['field_type'] = 'text'
            if _SSN_LABEL_RE.search(spec.get('field_label') or ''):
                spec['field_type'] = 'last4'

        # Group radio markers (small boxes) into checkbox_choice groups.
        markers = []
        texts = []
        for spec in typed_fields:
            wname = (spec.get('placeholder') or '').replace(ACRO_PLACEHOLDER_PREFIX, '')
            page_h = page_heights.get(spec['page_number'], 792)
            scale = SIGN_VIEWER_HEIGHT / float(page_h)
            pw = (spec.get('width') or 24) / scale
            ph = (spec.get('height') or 18) / scale
            rect_pdf = [
                spec['x_position'] / scale,
                spec['y_position'] / scale,
                spec['x_position'] / scale + pw,
                spec['y_position'] / scale + ph,
            ]
            label = (spec.get('field_label') or '').strip()
            option_like = label.lower() in {
                'single', 'married', 'male', 'female', 'yes', 'no',
                'black/african american', 'american indian', 'asian',
                'native hawaiian/pacific islanders', 'hispanic/spanish',
                'white (caucasian', 'employee handbook received',
                'harassment training completed', 'technical training received',
                'hepatitis b vaccine declination',
                'safety data sheets/safety handbook reviewed',
                'urethane liner safety received (rhino technician only',
            } or _is_acro_radio_marker(rect_pdf)
            if option_like and pw <= 45:
                markers.append({**spec, '_rect_pdf': rect_pdf})
            else:
                texts.append(spec)

        typed_fields[:] = texts
        by_page: dict[int, list] = {}
        for m in markers:
            by_page.setdefault(m['page_number'], []).append(m)

        def _append_marker_field(item: dict) -> None:
            item.pop('_rect_pdf', None)
            typed_fields.append(item)

        for page_num, page_markers in by_page.items():
            lines = page_lines.get(page_num - 1, [])
            # Vertical stacks (race/ethnicity column at same X)
            by_x: dict[int, list] = {}
            for m in page_markers:
                xkey = int(round(m['_rect_pdf'][0] / 12))
                by_x.setdefault(xkey, []).append(m)
            remaining_markers = []
            for xkey, col in by_x.items():
                col.sort(key=lambda s: s['_rect_pdf'][1])
                if len(col) >= 4 and all(
                    _acro_option_category(c.get('field_label') or '') == 'race' for c in col
                ):
                    group_key = _slug_group_name('Race / Ethnicity', page_num, str(xkey))
                    for c in col:
                        c['field_type'] = 'checkbox_choice'
                        c['choice_group'] = group_key
                        c['is_required'] = False
                        _append_marker_field(c)
                else:
                    remaining_markers.extend(col)

            sorted_m = sorted(remaining_markers, key=lambda s: (round(s['_rect_pdf'][1] / 8), s['_rect_pdf'][0]))
            row_clusters: list[list] = []
            for m in sorted_m:
                placed = False
                for cluster in row_clusters:
                    cy = sum(x['_rect_pdf'][1] for x in cluster) / len(cluster)
                    if abs(m['_rect_pdf'][1] - cy) <= 8:
                        cluster.append(m)
                        placed = True
                        break
                if not placed:
                    row_clusters.append([m])

            for cluster in row_clusters:
                for sub in _split_mixed_option_clusters(cluster):
                    if len(sub) < 2:
                        sub[0]['field_type'] = 'checkbox_choice'
                        sub[0]['choice_group'] = None
                        sub[0]['is_required'] = False
                        _append_marker_field(sub[0])
                        continue
                    labels = [(c.get('field_label') or '').strip() for c in sub]
                    if len(sub) == 2 and not _is_exclusive_choice_pair(labels):
                        for c in sub:
                            c['field_type'] = 'checkbox_choice'
                            c['choice_group'] = None
                            c['is_required'] = False
                            _append_marker_field(c)
                        continue
                    if any((c.get('width') or 0) > 55 for c in sub):
                        for c in sub:
                            c['field_type'] = 'text'
                            c['choice_group'] = None
                            _append_marker_field(c)
                        continue
                    labels_lower = [(c.get('field_label') or '').strip().lower() for c in sub]
                    if not all(
                        lb in _KNOWN_ACRO_OPTION_LABELS or _is_acro_radio_marker(c['_rect_pdf'])
                        for lb, c in zip(labels_lower, sub)
                    ):
                        for c in sub:
                            c['field_type'] = 'text'
                            c['choice_group'] = None
                            _append_marker_field(c)
                        continue
                    union = sub[0]['_rect_pdf'][:]
                    for c in sub[1:]:
                        r = c['_rect_pdf']
                        union[0] = min(union[0], r[0])
                        union[1] = min(union[1], r[1])
                        union[2] = max(union[2], r[2])
                        union[3] = max(union[3], r[3])
                    labels = [(c.get('field_label') or '').strip() for c in sub]
                    labels_lower = [l.lower() for l in labels]
                    if 'Single' in labels and 'Married' in labels:
                        default_group_label = 'Marital status'
                        pair_clusters = [sub]
                    elif 'Male' in labels and 'Female' in labels:
                        default_group_label = 'Gender'
                        pair_clusters = [sub]
                    elif all(l in ('yes', 'no') for l in labels_lower) and len(sub) > 2:
                        sub.sort(key=lambda c: c['_rect_pdf'][0])
                        pair_clusters = [sub[i:i + 2] for i in range(0, len(sub), 2)]
                        default_group_label = 'Yes / No'
                    elif all(l in ('yes', 'no') for l in labels_lower):
                        default_group_label = 'Yes / No'
                        pair_clusters = [sub]
                    else:
                        default_group_label = (
                            _label_left_of_rect(lines, union)
                            or _label_above_rect(lines, union)
                            or 'Select one'
                        )
                        pair_clusters = [sub]
                    for pair in pair_clusters:
                        if len(pair) < 2:
                            pair[0]['field_type'] = 'checkbox_choice'
                            pair[0]['is_required'] = False
                            _append_marker_field(pair[0])
                            continue
                        pair_union = pair[0]['_rect_pdf'][:]
                        for c in pair[1:]:
                            r = c['_rect_pdf']
                            pair_union[0] = min(pair_union[0], r[0])
                            pair_union[1] = min(pair_union[1], r[1])
                            pair_union[2] = max(pair_union[2], r[2])
                            pair_union[3] = max(pair_union[3], r[3])
                        pair_labels = [(c.get('field_label') or '').strip() for c in pair]
                        if 'Single' in pair_labels and 'Married' in pair_labels:
                            gl = 'Marital status'
                        elif 'Male' in pair_labels and 'Female' in pair_labels:
                            gl = 'Gender'
                        elif all(l.lower() in ('yes', 'no') for l in pair_labels):
                            gl = (
                                _label_left_of_rect(lines, pair_union)
                                or _label_above_rect(lines, pair_union)
                                or default_group_label
                            )
                        else:
                            gl = default_group_label
                        group_key = _slug_group_name(
                            gl, page_num, str(int(round(pair_union[1]))) + str(int(round(pair_union[0]))),
                        )
                        for c in pair:
                            c['field_type'] = 'checkbox_choice'
                            c['choice_group'] = group_key
                            opt_label = (c.get('field_label') or 'Option').strip()
                            c['field_label'] = opt_label[:200]
                            c['is_required'] = False
                            _append_marker_field(c)

        # Race fields that landed as singles — regroup if enough remain
        race_labels = {
            'black/african american', 'american indian', 'asian',
            'native hawaiian/pacific islanders', 'hispanic/spanish', 'white (caucasian',
        }
        race_fields = [
            s for s in typed_fields
            if s.get('field_type') == 'checkbox_choice'
            and (s.get('field_label') or '').lower() in race_labels
        ]
        if len(race_fields) >= 4:
            gkey = _slug_group_name('Race / Ethnicity', race_fields[0]['page_number'])
            for s in race_fields:
                s['choice_group'] = gkey

        # Auto typed_name for primary employee name field
        for spec in typed_fields:
            wname = (spec.get('placeholder') or '').replace(ACRO_PLACEHOLDER_PREFIX, '')
            if wname == 'Employee_Name':
                spec['field_type'] = 'typed_name'
                spec['field_label'] = 'Employee name'
            elif wname == 'Employee_SSN_Last4':
                spec['field_type'] = 'last4'
                spec['field_label'] = 'Social Security Number (last 4)'
            elif wname in ('Employee_Birthdate', 'Employee_Signature_Date', 'Manager_Signature_Date'):
                spec['field_type'] = 'date'
            elif wname in (
                'Dependent_1_Birthdate', 'Dependent_2_Birthdate', 'Dependent_3_Birthdate',
            ):
                spec['field_type'] = 'date'
            elif wname in (
                'Employee_Phone_Number',
                'Emergency_Contact_1_Home_Phone', 'Emergency_Contact_1_Cell_Phone',
                'Emergency_Contact_1_Work_Phone', 'Emergency_Contact_2_Home_Phone',
                'Emergency_Contact_2_Cell_Phone', 'Emergency_Contact_2_Work_Phone',
            ):
                spec['field_type'] = 'phone'
            elif ':signer:fullname' in wname.lower() and spec.get('field_type') == 'text':
                if not spec.get('field_label') or spec['field_label'].lower() == 'name':
                    spec['field_label'] = 'Name'

        _apply_ee_canonical_choice_groups(typed_fields)

        # Strip choice groups from non-choice field types.
        for spec in typed_fields:
            if spec.get('field_type') in ('last4', 'typed_name', 'date', 'text', 'number', 'phone'):
                spec['choice_group'] = None

        typed_fields.sort(key=lambda s: (s.get('page_number') or 1, s.get('y_position') or 0, s.get('x_position') or 0))
        signature_fields.sort(key=lambda s: (s.get('page_number') or 1, s.get('y_position') or 0))
    finally:
        doc.close()


def collect_acroform_import_specs(pdf_path: str) -> dict:
    """
    Read native AcroForm widgets (e.g. from Adobe Acrobat) for import into Document*Field rows.
    Returns signature_fields and typed_fields lists with viewer-pixel coordinates.
    """
    if not FITZ_AVAILABLE:
        return {'ok': False, 'error': 'PyMuPDF is not installed.', 'widget_count': 0}
    if not pdf_path or not os.path.isfile(pdf_path):
        return {'ok': False, 'error': 'PDF file not found.', 'widget_count': 0}

    signature_fields = []
    typed_fields = []
    seen_keys: set[str] = set()

    doc = fitz.open(pdf_path)
    try:
        for page_index in range(doc.page_count):
            page = doc[page_index]
            page_h = page.rect.height
            for w in page.widgets() or []:
                wtype = getattr(w, 'field_type', None)
                if wtype in (0, None):
                    continue
                dedupe_key = _acro_widget_dedupe_key(w, page_index)
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                wname = (w.field_name or '').strip()
                try:
                    from ee_pdf_field_map import canonical_acro
                    wname = canonical_acro(wname)
                except ImportError:
                    pass
                rect = list(w.rect) if w.rect else None
                if not rect or len(rect) != 4:
                    continue
                x, y, width, height = pdf_rect_to_viewer_coords(rect, page_h)
                page_number = page_index + 1
                placeholder = f'{ACRO_PLACEHOLDER_PREFIX}{wname}' if wname else None
                label = (w.field_label or wname or '').strip()
                if not label or label.lower() == 'undefined':
                    label = wname or f'Field on page {page_index + 1}'
                if wname in ('Employee_Signature', 'Manager_Signature') or (
                    'signature' in wname.lower() and 'signer' in wname.lower()
                ):
                    role = 'Employee' if 'Employee' in wname or wname.endswith('1') else 'Manager'
                    if wname == 'Manager_Signature':
                        role = 'Manager'
                    elif wname == 'Employee_Signature':
                        role = 'Employee'
                    signature_fields.append({
                        'page_number': page_number,
                        'x_position': x,
                        'y_position': y,
                        'width': max(width, 120.0),
                        'height': max(height, 50.0),
                        'field_label': f'{role} signature',
                        'is_required': role == 'Employee',
                    })
                    continue

                if getattr(w, 'field_type', None) == 6:
                    signature_fields.append({
                        'page_number': page_number,
                        'x_position': x,
                        'y_position': y,
                        'width': max(width, 120.0),
                        'height': max(height, 50.0),
                        'field_label': label[:200],
                        'is_required': True,
                    })
                    continue

                field_type = _widget_to_app_typed_field_type(w, label)
                choice_group = None
                if field_type == 'checkbox_choice':
                    choice_group = _acro_choice_group(wname) or label[:100]
                    if wtype == 5 and wname and '.' not in wname:
                        choice_group = wname[:100]
                typed_fields.append({
                    'page_number': page_number,
                    'x_position': x,
                    'y_position': y,
                    'width': width,
                    'height': height,
                    'field_label': label[:200],
                    'field_type': field_type,
                    'choice_group': choice_group,
                    'placeholder': placeholder,
                    'is_required': False if field_type == 'checkbox_choice' else True,
                })
    finally:
        doc.close()

    _enrich_acroform_import_specs(pdf_path, signature_fields, typed_fields)

    widget_count = len(signature_fields) + len(typed_fields)
    return {
        'ok': True,
        'signature_fields': signature_fields,
        'typed_fields': typed_fields,
        'widget_count': widget_count,
    }


def acro_value_for_widget(widget, field_value: str, field_type: str) -> str:
    """Convert app field value to PDF widget field_value."""
    val = (field_value or '').strip()
    wtype = getattr(widget, 'field_type', 1)
    if wtype in (2, 5) or field_type == 'checkbox_choice':
        if val.upper() in ('X', '1', 'TRUE', 'YES', 'ON'):
            if wtype == 5:
                on = getattr(widget, 'on_state', None) or getattr(widget, 'button_caption', None)
                return (on or 'Yes') if on else 'Yes'
            return 'Yes'
        return 'Off'
    return val


def viewer_coords_to_pdf_rect(
    page,
    x_viewer: float,
    y_viewer: float,
    width_viewer: float,
    height_viewer: float,
):
    """Map sign-page viewer pixels to a PDF rect on this page."""
    page_height = page.rect.height
    page_width = page.rect.width
    scale_y = page_height / SIGN_VIEWER_HEIGHT
    viewer_width_px = SIGN_VIEWER_HEIGHT * (page_width / page_height)
    scale_x = page_width / viewer_width_px
    x0 = float(x_viewer) * scale_x
    y0 = float(y_viewer) * scale_y
    return fitz.Rect(
        x0,
        y0,
        x0 + float(width_viewer) * scale_x,
        y0 + float(height_viewer) * scale_y,
    )


def _place_text_in_pdf_rect(page, rect, text: str, *, fontsize: int | None = None) -> None:
    val = (text or '').strip()
    if not val or rect.is_empty or rect.width <= 0 or rect.height <= 0:
        return
    fs = fontsize
    if fs is None:
        fs = int(rect.height * 0.75)
        fs = max(8, min(fs, 72))
    try:
        rc = page.insert_textbox(
            rect, val, fontsize=fs, align=0, color=(0, 0, 0), render_mode=0,
        )
        if rc < 0:
            page.insert_text((rect.x0 + 2, rect.y0 + fs + 1), val[:200], fontsize=fs, color=(0, 0, 0))
    except Exception:
        try:
            page.insert_text((rect.x0 + 2, rect.y0 + fs + 1), val[:200], fontsize=fs, color=(0, 0, 0))
        except Exception:
            pass


def embed_typed_field_values_in_pdf(pdf_doc, typed_fields, typed_value_map: dict) -> None:
    """
    Render saved typed/checkbox values onto the PDF.
    Uses on-page widget updates plus text overlay so values appear in all viewers.
    """
    try:
        from ee_pdf_field_map import canonical_acro
    except ImportError:
        canonical_acro = lambda n: (n or '').strip()  # noqa: E731

    by_acro: dict[str, list[tuple]] = {}
    for tf in typed_fields:
        tid = getattr(tf, 'id', None)
        if tid is None or tid not in typed_value_map:
            continue
        val = (typed_value_map[tid] or '').strip()
        if not val:
            continue
        ph = (getattr(tf, 'placeholder', None) or '').strip()
        ak = canonical_acro(ph[len(ACRO_PLACEHOLDER_PREFIX):]) if ph.startswith(ACRO_PLACEHOLDER_PREFIX) else ''
        if ak:
            by_acro.setdefault(ak, []).append((tf, val))

    for page in pdf_doc:
        for widget in page.widgets() or []:
            wname = canonical_acro((widget.field_name or '').strip())
            entries = by_acro.get(wname)
            if not entries:
                continue
            tf, val = entries[0]
            ft = getattr(tf, 'field_type', None) or 'text'
            try:
                widget.field_value = acro_value_for_widget(widget, val, ft)
                widget.update()
            except Exception:
                pass

    for tf in typed_fields:
        tid = getattr(tf, 'id', None)
        if tid is None or tid not in typed_value_map:
            continue
        val = (typed_value_map[tid] or '').strip()
        if not val:
            continue
        page_num = int(getattr(tf, 'page_number', 1) or 1) - 1
        if page_num < 0 or page_num >= len(pdf_doc):
            continue
        page = pdf_doc[page_num]
        rect = viewer_coords_to_pdf_rect(
            page,
            getattr(tf, 'x_position', 0) or 0,
            getattr(tf, 'y_position', 0) or 0,
            getattr(tf, 'width', 200) or 200,
            getattr(tf, 'height', 30) or 30,
        )
        ft = getattr(tf, 'field_type', None) or 'text'
        if ft == 'checkbox_choice':
            if val.upper() == 'X':
                _place_text_in_pdf_rect(page, rect, 'X', fontsize=max(8, int(rect.height * 0.85)))
        else:
            _place_text_in_pdf_rect(page, rect, val)


def embed_signatures_in_pdf(pdf_doc, user_signatures, signature_fields) -> None:
    """Place drawn signatures using AcroForm widget rects when available."""
    try:
        from ee_pdf_field_map import EE_SIGNATURE_ACROS
        sig_acros = EE_SIGNATURE_ACROS
    except ImportError:
        sig_acros = {'employee': 'Employee_Signature', 'manager': 'Manager_Signature'}

    widget_rects: dict[str, tuple[int, object]] = {}
    for page_idx, page in enumerate(pdf_doc):
        for widget in page.widgets() or []:
            wname = (widget.field_name or '').strip()
            for role, acro in sig_acros.items():
                if wname == acro and widget.rect and not widget.rect.is_empty:
                    widget_rects[role] = (page_idx, widget.rect)

    field_by_id = {f.id: f for f in signature_fields if getattr(f, 'id', None)}

    for sig in user_signatures:
        if not sig.signature_image:
            continue
        role = None
        field = field_by_id.get(sig.signature_field_id) if sig.signature_field_id else None
        if field:
            lbl = (field.field_label or '').lower()
            role = 'manager' if 'manager' in lbl else 'employee'

        page = None
        img_rect = None
        if role and role in widget_rects:
            page_idx, target_rect = widget_rects[role]
            page = pdf_doc[page_idx]
            img_rect = fitz.Rect(target_rect)
        elif field:
            page_num = int(getattr(field, 'page_number', 1) or 1) - 1
            if page_num < 0 or page_num >= len(pdf_doc):
                continue
            page = pdf_doc[page_num]
            img_rect = viewer_coords_to_pdf_rect(
                page,
                getattr(field, 'x_position', 0) or 0,
                getattr(field, 'y_position', 0) or 0,
                getattr(field, 'width', 200) or 200,
                getattr(field, 'height', 50) or 50,
            )
        else:
            continue

        try:
            from PIL import Image
            sig_image_data = base64.standard_b64decode(sig.signature_image)
            sig_img = Image.open(BytesIO(sig_image_data))
            img_bytes = BytesIO()
            sig_img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            page.insert_image(img_rect, stream=img_bytes.getvalue(), keep_proportion=True)
        except Exception:
            continue
