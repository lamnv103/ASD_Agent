"""Loss-aware OOXML supplement conversion, kept inside its parent source file."""
from __future__ import annotations
import html
import io
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
C='http://schemas.openxmlformats.org/drawingml/2006/chart'
A='http://schemas.openxmlformats.org/drawingml/2006/main'

def local(n):return n.tag.split('}')[-1]

def chart_text(raw):
    root=ET.fromstring(raw);ns={'c':C,'a':A}
    supported=root.findall('.//c:barChart',ns)
    if len(supported)!=1:raise ValueError('Unsupported chart type; keep conversion pending')
    parts=['[Original bar-chart data; converted directly from OOXML caches, no inferred values.]']
    titles=[''.join(n.itertext()) for n in root.findall('.//c:title//a:t',ns)]
    if titles:parts.append(' / '.join(titles))
    for series in root.findall('.//c:ser',ns):
        name=[n.text or '' for n in series.findall('c:tx//c:v',ns)]
        cats=series.findall('c:cat//c:pt',ns);vals=series.findall('c:val//c:pt',ns)
        if not cats or len(cats)!=len(vals):raise ValueError('Chart category/value count mismatch')
        cdict={n.get('idx'):''.join(n.find('c:v',ns).itertext()) for n in cats}
        vdict={n.get('idx'):''.join(n.find('c:v',ns).itertext()) for n in vals}
        if cdict.keys()!=vdict.keys():raise ValueError('Chart point indices mismatch')
        parts.append('Series: '+(' / '.join(name) if name else '[not labelled in chart]'))
        parts.append('<table><tr><th>Category</th><th>Value (as printed in chart cache)</th></tr>'+
                     ''.join('<tr><td>'+html.escape(cdict[k])+'</td><td>'+html.escape(vdict[k])+'</td></tr>' for k in sorted(cdict,key=int))+'</table>')
    return '\n\n'.join(parts)

def convert_docx(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=set(z.namelist());document=ET.fromstring(z.read('word/document.xml'))
        relationships={}
        if 'word/_rels/document.xml.rels' in names:
            for n in ET.fromstring(z.read('word/_rels/document.xml.rels')):
                relationships[n.get('Id')]=n.attrib
        gaps=[];charts=[]
        def render_table(table):
            active={};rows=[]
            for row in table.findall('{'+W+'}tr'):
                cells=[];new_active={};col=0
                for cell in row.findall('{'+W+'}tc'):
                    prop=cell.find('{'+W+'}tcPr')
                    span=prop.find('{'+W+'}gridSpan') if prop is not None else None
                    width=int(span.get('{'+W+'}val')) if span is not None else 1
                    merge=prop.find('{'+W+'}vMerge') if prop is not None else None
                    value=''.join(render(c) for c in cell if local(c)!='tcPr').strip()
                    continuation=merge is not None and merge.get('{'+W+'}val','continue')=='continue'
                    if continuation:
                        previous=active.get(col)
                        if previous is None or previous['width']!=width:
                            gaps.append({'type':'docx_invalid_vertical_merge'})
                            previous={'value':value,'width':width,'height':1};cells.append(previous)
                        else:
                            previous['height']+=1
                            if value:previous['value']+='\n\n'+value
                        new_active[col]=previous
                    else:
                        item={'value':value,'width':width,'height':1};cells.append(item)
                        if merge is not None:new_active[col]=item
                    col+=width
                rows.append(cells);active=new_active
            return '\n\n<table>'+''.join('<tr>'+''.join('<td'+
                (' colspan="'+str(c['width'])+'"' if c['width']>1 else '')+
                (' rowspan="'+str(c['height'])+'"' if c['height']>1 else '')+
                '>'+c['value']+'</td>' for c in row)+'</tr>' for row in rows)+'</table>\n\n'
        def render(n):
            tag=local(n)
            if tag in {'del','moveFrom'}:return '' # accepted document view; original tracked XML retained
            if tag=='t':return html.escape(n.text or '',quote=False)
            if tag=='tab':return ' '
            if tag in {'br','cr'}:return '\n'
            if tag=='chart':
                rel=relationships.get(n.get('{'+R+'}id'))
                if rel is None:raise ValueError('Chart relationship missing')
                target=posixpath.normpath(posixpath.join('word',rel['Target']))
                if not target.startswith('word/charts/'):raise ValueError('Invalid chart part')
                charts.append(target)
                return '\n\n'+chart_text(z.read(target))+'\n\n'
            if tag in {'blip','imagedata','altChunk','object'}:
                gaps.append({'type':'unconverted_docx_'+tag});return ''
            if tag=='tbl':return render_table(n)
            content=''.join(render(c) for c in n)
            if tag=='hyperlink':
                rel=relationships.get(n.get('{'+R+'}id'))
                return '['+content+']('+rel['Target']+')' if rel and rel.get('TargetMode')=='External' else content
            if tag=='p':return content+'\n\n'
            if tag=='tbl':return '\n\n<table>'+content+'</table>\n\n'
            if tag=='tr':return '<tr>'+content+'</tr>'
            if tag=='tc':
                span=n.find('{'+W+'}tcPr/{'+W+'}gridSpan')
                vertical=n.find('{'+W+'}tcPr/{'+W+'}vMerge')
                if vertical is not None:gaps.append({'type':'docx_vertical_merge_needs_layout_review'})
                attrs=' colspan="'+span.get('{'+W+'}val')+'"' if span is not None else ''
                return '<td'+attrs+'>'+content.strip()+'</td>'
            return content
        body=render(document.find('{'+W+'}body'))
        # Footnotes/endnotes contain source information too, not page furniture.
        for part in ['word/footnotes.xml','word/endnotes.xml']:
            if part in names:
                node=ET.fromstring(z.read(part))
                body+='\n\n'+render(node)
        from library import clean,fidelity_text,digest
        body=clean(body)
        visible=[''.join(n.itertext()) for n in document.iter() if local(n)=='t']
        normalized=fidelity_text(body,rendered=True)
        missing=[s for s in visible if s.strip() and fidelity_text(s) not in normalized]
        if missing:gaps.append({'type':'docx_text_fidelity','missing_runs':missing})
        return body,{'format':'docx','checked_text_runs':len(visible),'charts':charts,'gaps':gaps,
                     'body_sha256':digest(body),'part':'word/document.xml'}
