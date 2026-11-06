"""Loss-aware whole-document conversion; deliberately no chunking/model/DB code."""
from __future__ import annotations

import copy
from pathlib import Path
import hashlib
import html
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from markdownify import markdownify, MarkdownConverter

SCHEMA = 'carobud.source-library.v2'
CHECKED = '2026-10-17'  # Date of source snapshots; not the conversion-build date.
CONVERSION_REVISION = 'jats-readable-front-v3-20261020'
MARKER = '<!-- ORIGINAL_DOCUMENT_BODY -->'


def digest(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode('utf-8')).hexdigest()


def text(node):
    return ' '.join(''.join(node.itertext()).split()) if node is not None else ''


def clean(value):
    # Formatting only: never normalize numbers, terminology or professional claims.
    return re.sub(r'\n{3,}', '\n\n', value).strip() + '\n'


def canonicalize_with_spans(value,units):
    """Canonical whitespace exactly once, translating every native offset."""
    removed=[(m.start()+2,m.end()) for m in re.finditer(r'\n{3,}',value)]
    normalized=re.sub(r'\n{3,}','\n\n',value)
    leading=len(normalized)-len(normalized.lstrip())
    body=normalized.strip()+'\n'
    def translate(position):
        deleted=sum(max(0,min(position,end)-start) for start,end in removed)
        return max(0,min(len(body)-1,position-deleted-leading))
    translated=[]
    for item in units:
        unit=dict(item);start=translate(unit['start']);end=translate(unit['end'])
        while start<end and body[start].isspace():start+=1
        while end>start and body[end-1].isspace():end-=1
        unit.update(start=start,end=end,rendered_section_sha256=digest(body[start:end]))
        translated.append(unit)
    return body,translated


def comparable(value):
    """Bibliographic comparison only; never used to certify clinical text."""
    value = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', value)
    value = re.sub(r'</?(?:bold|italic|sup|sub|em|strong|span)\b[^>]*>', '', value)
    return ''.join(c for c in html.unescape(value) if c.isalnum()).casefold()


def fidelity_text(value, rendered=False):
    """Normalize presentation whitespace, preserving numbers, signs and words."""
    if rendered:
        value=re.sub(r'\[([^\]]*)\]\([^)]*\)',r'\1',value)
        value=re.sub(r'</?(?:bold|italic|sup|sub|em|strong|span|table|thead|tbody|tfoot|tr|td|th)\b[^>]*>','',value)
        value=re.sub(r'\\([*_[\]`])',r'\1',value)
    return re.sub(r'\s+','',html.unescape(value))


def source_flow_blocks(article, excluded_nodes=None):
    """Check text runs around nested blocks without mistaking list markup for loss.

    JATS sometimes nests a complete list/figure/table inside a paragraph. Its
    flattened itertext is not contiguous after a correct Markdown conversion.
    Check all runs and the nested blocks separately; never strip clinical minus
    signs or comparison operators to make a comparison pass.
    """
    structural={'p','sec','list','list-item','fig','table-wrap','table','thead',
                'tbody','tfoot','tr','td','th','boxed-text','caption','title',
                'supplementary-material','fn','disp-formula','inline-formula','graphic','inline-graphic','media','article-title','subtitle'}
    check_tags={'p','list-item','td','th','caption','title','article-title','subtitle','fn'}
    excluded=set(excluded_nodes or ())
    def kept_nodes(node):
        if node in excluded:return
        yield node
        for child in node:yield from kept_nodes(child)
    blocks=[]
    for node in kept_nodes(article):
        if node.tag not in check_tags:continue
        pieces=[node.text or '']
        for child in node:
            if child in excluded:
                pieces.append(child.tail or '')
                continue
            if child.tag in structural:
                value=' '.join(''.join(pieces).split())
                if value:blocks.append(value)
                pieces=[]
            else:pieces.append(''.join(child.itertext()))
            pieces.append(child.tail or '')
        value=' '.join(''.join(pieces).split())
        if value:blocks.append(value)
    return blocks


def article_title(article):
    group=article.find('front/article-meta/title-group')
    if group is None:return ''
    title=text(group.find('article-title'))
    subtitles=[text(n) for n in group.findall('subtitle') if text(n)]
    return ': '.join([title]+subtitles)


def base_record(source_id, title, url, source_type):
    return dict(schema_version=SCHEMA, source_id=source_id, aliases=[], title=title,
                authors=[], organization=None, source_url=url, language=None,
                publication_date=None, updated_date=None, version=None,
                source_type=source_type, checked_at=CHECKED,
                clinical_reviewed=False, risk_of_bias_appraisal='not_done',
                review_agent='AI source/provenance and conversion audit; not independent clinical review',
                status='pending', document_path=None, original_age_scope=None,
                applicability_0_18_years='unconfirmed', topics=[], limits=[],
                rights={'status': 'unverified', 'license': None, 'evidence_url': None},
                conversion={'status': 'not_attempted', 'gaps': []},
                embedding={'unit': 'not_selected_preview_only', 'requested': False,
                           'model_candidate': 'gemini-embedding-2', 'input_limit_tokens': 8192,
                           'token_count': None, 'length_status': 'unknown',
                           'status': 'pending_compatible_token_count',
                           'truncate': False, 'split': False},
                index_preview={'requested': True, 'final_chunk_strategy': False},
                prototype_ingest=False, production_ingest=False)


def make_document(record, body):
    def shown(v):
        return v or 'Không được nguồn công bố / chưa xác minh'
    author = '; '.join(record['authors']) or record.get('organization')
    scope=record.get('content_scope') or record.get('original_age_scope') or 'Chưa xác định'
    if isinstance(scope,dict):scope=scope.get('reason') or 'Phạm vi tuổi chưa chốt; bằng chứng gốc được ghi trong catalog.jsonl'
    header = (f'# {record["title"]}\n\n'
              f'Tên tài liệu: {record["title"]}\n\n'
              f'Tác giả hoặc tổ chức: {shown(author)}\n\n'
              f'Link nguồn: {record["source_url"]}\n\n'
              f'Ngày xuất bản: {shown(record.get("publication_date"))}\n\n'
              f'Ngày cập nhật: {shown(record.get("updated_date"))}; phiên bản: {shown(record.get("version"))}\n\n'
              f'Phạm vi nội dung: {scope}\n\n'
              f'ID nguồn: {record["source_id"]}\n\n'
              f'Giấy phép: {shown(record["rights"].get("license"))}. '
              f'Căn cứ: {record["rights"].get("evidence_url")}\n\n'
              f'Trạng thái chuyển đổi: {record["conversion"]["status"]}. '
              'Giới hạn chuyển đổi và phạm vi sử dụng được ghi trong catalog.jsonl.\n\n'
              'Bản đối chiếu phục vụ nghiên cứu; chưa có thẩm định lâm sàng độc lập.\n\n'
              '---\n\n## NỘI DUNG NGUYÊN BẢN\n\n' + MARKER + '\n')
    return header + clean(body)


def convert_html(raw, url, family):
    soup = BeautifulSoup(raw, 'html.parser')
    title = soup.h1.get_text(' ', strip=True) if soup.h1 else None
    if not title:
        raise ValueError('Missing document title (possibly access-denied HTML)')
    if family == 'cdc':
        node = soup.select_one('.cdc-dfe-body')
    elif family == 'nimh':
        node = soup.select_one('article')
    else:
        raise ValueError('No generic full-page fallback: selector must be verified')
    if node is None:
        raise ValueError('Missing verified article selector')
    node = copy.deepcopy(node)
    # Only site UI / duplicate social controls. Do not remove article callouts,
    # reference lists, warning boxes, hidden article accordion text or tables.
    for el in node.select('script,style,nav,form,button,.cdc-share,.social-share,.addthis_toolbox'):
        el.decompose()
    for el in node.find_all(['a', 'img']):
        attr = 'href' if el.name == 'a' else 'src'
        if el.get(attr):
            el[attr] = urljoin(url, el[attr])
    media = []
    for image in node.find_all('img'):
        media.append({'type': 'image', 'alt': image.get('alt'), 'url': image.get('src'),
                      'status': 'linked_not_transcribed'})
        # CDC/NIMH text permissions do not automatically license all photographs.
        alt = image.get('alt') or 'Image'
        image.replace_with(soup.new_string(f' [Image in original: {alt}; {image.get("src", url)}] '))
    for embedded in node.find_all(['iframe', 'video', 'audio']):
        media.append({'type': embedded.name, 'url': embedded.get('src'),
                      'status': 'not_transcribed'})
        embedded.replace_with(soup.new_string(f' [Media in original: {embedded.get("src", url)}] '))
    original_plain = node.get_text(' ', strip=True)
    class TablesIntact(MarkdownConverter):
        def convert_table(self,el,text,parent_tags):
            return '\n\n'+str(el)+'\n\n'
    body = clean(TablesIntact(heading_style='ATX',bullets='-',strip=['span']).convert(str(node)))
    # Verify complete text stream survives conversion, not merely first/last para.
    # HTML-table Markdown can add separators, links can add URLs: ordered blocks
    # are checked separately instead of misleading equality after normalization.
    blocks = [p.get_text(' ', strip=True) for p in node.find_all(['p', 'li', 'th', 'td', 'h2', 'h3', 'h4'])]
    normalized = comparable(body)
    missing = [b for b in blocks if len(b) > 20 and comparable(b) not in normalized]
    metadata = {}
    for m in soup.find_all('meta'):
        name = m.get('name') or m.get('property')
        if name:
            metadata[name] = m.get('content')
    return body, dict(title=title, html_metadata=metadata,
                      input_text_characters=len(original_plain), checked_blocks=len(blocks),
                      unmatched_blocks=missing, media=media,
                      headings=[x.get_text(' ', strip=True) for x in node.find_all(['h2', 'h3', 'h4'])],
                      html_heading_anchors=[{'title':x.get_text(' ',strip=True),'id':x.get('id'),'level':int(x.name[1])} for x in node.find_all(['h2','h3','h4'])],
                      removals=['script/style/navigation/forms/buttons/social UI','Images not copied; original captions/links retained'])


def convert_cdc_web(raw):
    """Retain the entire article text of the public web-reader representation.

    This is explicitly a conversion with gaps, not original HTML. Reject any
    excerpt with omitted lines; never label browser snippets as a full article.
    Link destinations and multimedia must be verified against original HTML.
    """
    total = re.search(r'Total lines: (\d+)', raw)
    entries = re.findall(r'(?:^|\s)L(\d+): ?(.*?)(?=(?:\sL\d+:)|\Z)', raw, re.S)
    lines = {int(n): value.strip() for n,value in entries}
    if not total or set(lines) != set(range(int(total[1]))):
        raise ValueError('Incomplete web-reader response; cannot substitute an excerpt')
    ordered=[lines[n] for n in range(int(total[1]))]
    start=next((n for n,value in enumerate(ordered) if value.startswith('# ')),None)
    if start is None:raise ValueError('No article h1')
    end=next((n for n in range(start+1,len(ordered)) if ordered[n].startswith('## \ue200cite')),len(ordered))
    body='\n\n'.join(ordered[start:end])
    # Reader labels keep original visible text. Do not invent missing hrefs.
    body=re.sub(r'\ue200cite\ue202[^†\ue201]+†([^\ue201]+)\ue201',lambda m:m[1].split('†')[0],body)
    body=re.sub(r'\ue200[^\ue201]*\ue201','',body)
    dates={}
    for key in ['Published','Updated','Reviewed']:
        found=re.search(r'\b'+key+r':\s*([^\n]+)',body)
        dates[key.lower()]=found[1].strip() if found else None
    return clean(body),{'title':ordered[start][2:], 'source_lines_verified':len(lines),
                        'original_total_lines':int(total[1]),'dates_as_printed':dates,
                        'method':'Public web-reader text, complete line set checked; original HTML unavailable',
                        'gaps':[{'type':'link_targets_and_multimedia','status':'needs_original_HTML_PDF_comparison',
                                 'reason':'Visible article text and source notes retained; original link destinations, images/video not fully preserved.'}]}


def xml_without_tag_namespaces(raw):
    root=ET.fromstring(raw)
    for node in root.iter():
        if isinstance(node.tag,str):node.tag=node.tag.split('}')[-1]
    return root


def licensed_oa(oa, article):
    """Require both official OA eligibility and an explicit recognized license."""
    root=xml_without_tag_namespaces(oa)
    record = root.find('.//record')
    if record is None or record.get('retracted', '').lower() == 'yes':
        return None
    if root.tag=='OAI-PMH':
        header=record.find('header')
        if header is None or header.get('status')=='deleted' or 'pmc-open' not in [text(n) for n in header.findall('setSpec')]:return None
        identifier=text(header.find('identifier'))
        evidence='https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/?verb=GetRecord&metadataPrefix=pmc&identifier='+identifier
    else:
        evidence='https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id='+record.get('id','')
    permissions = article.find('front/article-meta/permissions')
    urls = [n.get('{http://www.w3.org/1999/xlink}href', '') for n in article.findall('.//license')]
    raw = ' '.join(urls + [text(permissions), record.get('license', '')])
    # ND licenses are not accepted for conversion/AI reuse in this library.
    if re.search(r'(?:by-nd|by-nc-nd|no.?deriv)', raw, re.I):
        return None
    for slug in ('by-nc-sa', 'by-nc', 'by-sa', 'by'):
        found = re.search(r'https?://creativecommons\.org/licenses/' + slug + r'/[\d.]+/?', raw, re.I)
        if found:
            return {'status': 'verified_noncommercial_research', 'license': found.group(),
                    'evidence_url': evidence,
                    'license_text': text(permissions), 'third_party_exceptions': 'Retain per-figure credit lines; not adjudicated independently'}
    if 'creativecommons.org/publicdomain/zero/' in raw:
        return {'status': 'verified', 'license': 'CC0', 'evidence_url': evidence}
    return None


def separate_jats_metadata(article, paths):
    """Move named bibliographic/processing XML nodes out of source prose.

    Policies apply only at explicit front-matter paths. Never strip matching
    words from clinical prose, unknown author notes, or unknown custom fields.
    The original XML and each separated node remain available for inspection.
    """
    excluded=set(); separated=[]; removals=[]
    def move(node, kind):
        if node in excluded:return
        excluded.add(node)
        snapshot=copy.deepcopy(node);snapshot.tail=None
        xml=ET.tostring(snapshot,encoding='unicode')
        separated.append({'xml_xpath':paths[node],'tag':node.tag,
                          'attributes':dict(node.attrib),'source_xml':xml,
                          'source_xml_sha256':digest(xml)})
        removals.append({'type':kind,'xml_xpath':paths[node],
                         'source_xml_sha256':digest(xml),
                         'reason':'Bibliographic/repository metadata retained in the original XML and conversion metadata; excluded from clinical prose.'})
    front=article.find('front')
    if front is not None:
        for node in front.findall('journal-meta'):move(node,'bibliographic_metadata_separated')
        fields={'article-id','article-version','article-version-alternatives',
                'article-categories','pub-date','volume','issue','issue-id',
                'fpage','lpage','elocation-id','history','pub-history','counts','self-uri','related-object'}
        technical={'typesetter','cover-date','source-schema-version-number',
                   'details-of-publishers-convertor','section-at-acceptance'}
        for meta in front.findall('article-meta'):
            for node in meta:
                if node.tag in fields:move(node,'bibliographic_metadata_separated')
                elif node.tag=='custom-meta-group':
                    for custom in node.findall('custom-meta'):
                        name=text(custom.find('meta-name'))
                        if name.startswith(('pmc-status-','pmc-prop-','pmc-is-',
                                            'pmc-collection-','pmc-license-')) or name in technical:
                            move(custom,'repository_processing_metadata_separated')
    for node in article.findall('processing-meta'):
        move(node,'repository_processing_metadata_separated')
    return excluded,separated,removals


def convert_jats(raw):
    root = xml_without_tag_namespaces(raw)
    article = root if root.tag == 'article' else root.find('.//article')
    if article is None or article.find('body') is None:
        raise ValueError('No article full body; abstract is not full text')
    body_node = article.find('body')
    if len(text(body_node)) < 1000:
        raise ValueError('Implausibly short full article body')
    from source_assets import load_assets
    reviewed_assets=load_assets(digest(raw))
    used_assets=[]
    gaps=[];removals=[]
    paths={article:'/article'};parents={}
    def paths_for(node):
        counts={}
        for child in node:
            counts[child.tag]=counts.get(child.tag,0)+1
            paths[child]=paths[node]+f'/{child.tag}[{counts[child.tag]}]'
            parents[child]=node;paths_for(child)
    paths_for(article)
    excluded,separated_metadata,metadata_removals=separate_jats_metadata(article,paths)
    removals.extend(metadata_removals)
    tracked={n:str(i) for i,n in enumerate(body_node) if n.tag in {'sec','p','list','table-wrap','boxed-text'}}
    units={tracked[n]:{'xml_xpath':paths[n], 'section_path':[text(n.find('title')) or n.tag],
                        'source_text':text(n)} for n in tracked}
    if '\ue000' in text(article) or '\ue001' in text(article):raise ValueError('Reserved locator marker in source')
    unsupported={'inline-formula','disp-formula','chem-struct','speech','array','math'}

    def render(n,level=2):
        tag=n.tag
        if n in excluded:return ''
        children=[(c,render(c,level+(tag=='sec'))) for c in n]
        content=html.escape(n.text or '',quote=False)+''.join(value+html.escape(c.tail or '',quote=False) for c,value in children)
        supported_array=(tag=='array' and (n.find('tbody') is not None or n.find('table') is not None))
        supported_formula=(tag in {'inline-formula','disp-formula'} and (n.find('.//math') is not None or (bool(n.findall('.//graphic')) and all(paths[g] in reviewed_assets for g in n.findall('.//graphic')))))
        if tag in unsupported and tag!='math' and not supported_array and not supported_formula:gaps.append({'type':tag,'xml_xpath':paths[n],'status':'needs_visual_or_math_review'})
        if tag=='math':
            original_math=copy.deepcopy(n);original_math.tail=None
            original_math.set('xmlns','http://www.w3.org/1998/Math/MathML')
            result=ET.tostring(original_math,encoding='unicode')
        elif tag=='array' and supported_array:
            result='<table>'+content+'</table>'
        elif tag in {'article-title','subtitle'} and parents.get(n) is not None and parents[n].tag!='title-group':
            result=content  # reference/self-citation titles are inline, not new sections
        elif tag in {'title','article-title','subtitle'}:
            result='\n\n'+'#'*min(level,6)+' '+content.strip()+'\n\n'
        elif tag in {'p','sec','abstract','ref','fn','ack','app','bio','boxed-text','statement','table-wrap','fig','supplementary-material'}:
            result='\n\n'+content+'\n\n'
            if tag=='supplementary-material':
                media=n.findall('.//media')
                if not media or not all(paths[m] in reviewed_assets for m in media):
                    gaps.append({'type':tag,'xml_xpath':paths[n],'status':'external_supplement_not_transcribed'})
        elif tag=='list-item':result='\n- '+content.strip()+'\n'
        elif tag in {'name','string-name'}:
            # Whitespace separates original name components; do not infer name order.
            result=' '.join(v.strip() for v in [html.escape(n.text or '',quote=False)]+[value+html.escape(c.tail or '',quote=False) for c,value in children] if v.strip())
        elif tag=='custom-meta' and paths[n].startswith('/article/front['):
            fields={c.tag:value for c,value in children}
            result='\n\n'+fields['meta-name'].strip()+': '+fields['meta-value'].strip()+'\n\n' if set(fields)=={'meta-name','meta-value'} else '\n\n'+content+'\n\n'
        elif tag=='xref' and n.get('ref-type')=='aff':
            result=' '+content+' '
        elif tag in {'contrib-id','label','given-names','surname','copyright-statement','copyright-year','copyright-holder'}:
            result=content+' '
        elif tag in {'title-group','contrib-group','author-notes','aff','funding-group','permissions','kwd-group','notes','related-article'}:
            result='\n\n'+content+'\n\n'
            if tag=='related-article' and paths[n].startswith('/article/front[') and n.get('{http://www.w3.org/1999/xlink}href'):
                result+='\n'+n.get('{http://www.w3.org/1999/xlink}href')+'\n'
        elif tag in {'name','aff','contrib','pub-date','journal-meta','article-id','kwd','contrib-group','date','history'}:
            result='\n'+content+'\n'
        elif tag in {'bold','italic','sup','sub'}:result=f'<{tag}>{content}</{tag}>'
        elif tag in {'ext-link','uri'}:
            href=n.get('{http://www.w3.org/1999/xlink}href')
            result=f'[{content}]({href})' if href else content
        elif tag in {'graphic','inline-graphic','media'}:
            parent=parents.get(n)
            table_alternative=parent is not None and parent.tag=='alternatives' and (parent.find('table') is not None or parent.find('math') is not None)
            href=n.get('{http://www.w3.org/1999/xlink}href')
            paragraph=parents.get(n)
            orcid_icon=(tag=='inline-graphic' and paragraph is not None and paragraph.tag=='p'
                        and (('ORCID' in text(paragraph)) or
                             (parents.get(paragraph) is not None and parents[paragraph].tag=='fn'
                              and len(paragraph.findall('inline-graphic'))==1))
                        and any('orcid.org/' in c.get('{http://www.w3.org/1999/xlink}href','')
                                for c in paragraph.findall('ext-link')))
            asset=reviewed_assets.get(paths[n])
            if asset:
                if asset['original_href']!=href:raise ValueError('Asset review refers to different XML href')
                used_assets.append({k:v for k,v in asset.items() if k not in {'rendered_text','verbatim_text'}})
                label='Original figure transcription' if asset['kind']=='image' else 'Original supplementary document, full converted text'
                result=content+'\n\n['+label+'; formatting conversion, no interpretation]\n\n'+asset['rendered_text']+'\n\n'
                if asset['kind']=='image':result+='![Original figure](../originals/assets/'+asset['pmc']+'/'+Path(asset['archived_path']).name+')\n'
            elif table_alternative:result=''
            elif orcid_icon:
                result=''
                removals.append({'type':'decorative_orcid_icon','xml_xpath':paths[n],
                                 'reason':'ORCID identifier and author name retained as source text/link.'})
            else:
                gaps.append({'type':tag,'xml_xpath':paths[n],'original_href':href,'status':'asset_not_transcribed'})
                result=content+f'\n[Original asset: {href}; see source article]\n'
        elif tag in {'table','thead','tbody','tfoot','tr','th','td'}:
            attrs=''.join(f' {k}="{html.escape(v)}"' for k,v in n.attrib.items() if k in {'colspan','rowspan','scope','align'})
            result=f'<{tag}{attrs}>{content}</{tag}>'
        else:result=content
        if n in tracked:
            key=tracked[n];result=f'\ue000S{key}\ue001'+result+f'\ue000E{key}\ue001'
        return result

    front = article.find('front')
    parts = []
    # Keep substantive front matter, author notes, permissions and funding.
    # Bibliographic/processing nodes are stored separately, never deleted from originals.
    if front is not None:
        parts.append(render(front))
    parts.append(render(body_node))
    back = article.find('back')
    if back is not None:
        parts.append('\n\n## End matter (original)\n\n' + render(back))
    for el in article:
        if el.tag not in {'front', 'body', 'back','processing-meta'}:
            parts.append(render(el))  # floats, subarticles, responses, appendices
    marked=clean('\n\n'.join(parts));plain=[];last=0;position=0
    for match in re.finditer(r'\ue000([SE])(\d+)\ue001',marked):
        fragment=marked[last:match.start()];plain.append(fragment);position+=len(fragment)
        units[match[2]]['start' if match[1]=='S' else 'end']=position;last=match.end()
    plain.append(marked[last:]);untrimmed=''.join(plain)
    body,native_units=canonicalize_with_spans(untrimmed,units.values())
    normalized=fidelity_text(body,rendered=True)
    blocks=source_flow_blocks(article,excluded)
    unmatched=[p for p in blocks if fidelity_text(p) not in normalized]
    gaps.extend({'type':'text_fidelity','original_text':p,'status':'needs_conversion_review'} for p in unmatched)
    meta = dict(title=article_title(article),conversion_revision=CONVERSION_REVISION,
                separated_metadata=separated_metadata,
                body_characters=len(text(body_node)),
                paragraphs=len(body_node.findall('.//p')),checked_text_blocks=len(blocks),
                tables=len(article.findall('.//table')),
                figures=len(article.findall('.//fig')),
                references=len(article.findall('.//ref')), gaps=gaps,removals=removals,source_assets=used_assets,mathml_representations=len(article.findall('.//math')),native_units=native_units,
                headings=[text(n) for n in body_node.findall('.//sec/title')],
                last_original_body_text=text(body_node)[-240:])
    return article, body, meta


def pubmed_records(raw):
    records = []
    for item in ET.fromstring(raw).findall('.//PubmedArticle'):
        citation = item.find('MedlineCitation')
        article = citation.find('Article')
        ids = {n.get('IdType'): text(n) for n in item.findall('PubmedData/ArticleIdList/ArticleId')}
        if ids.get('pmc') and not ids['pmc'].startswith('PMC'):
            ids['pmc']='PMC'+ids['pmc']
        authors = []
        for author in article.findall('AuthorList/Author'):
            name = text(author.find('CollectiveName')) or ' '.join(filter(None, [text(author.find('ForeName')), text(author.find('LastName'))]))
            if name:
                authors.append(name)
        comments = [dict(type=n.get('RefType'), pmid=text(n.find('PMID')), note=text(n.find('Note'))) for n in citation.findall('CommentsCorrectionsList/CommentsCorrections')]
        pd=article.find('Journal/JournalIssue/PubDate')
        date_parts={c.tag:text(c) for c in pd} if pd is not None else {}
        date='-'.join(date_parts.get(k,'') for k in ['Year','Month','Day']).strip('-') or date_parts.get('MedlineDate')
        records.append(dict(pmid=text(citation.find('PMID')), title=text(article.find('ArticleTitle')),
                            authors=authors, ids=ids, abstract=text(article.find('Abstract')),
                            date=date, date_parts=date_parts,
                            publication_types=[text(n) for n in article.findall('PublicationTypeList/PublicationType')],
                            comments_corrections=comments))
    return records
