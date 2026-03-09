from docx import Document
from docx.oxml.ns import qn
from lxml import etree

doc = Document("Technical_Spesification_Document_(TSD)_-_MPM_Dom_(CR46881).docx")

# Print semua docDefaults raw XML
docDefaults = doc.element.find('.//' + qn("w:docDefaults"))
if docDefaults is not None:
    print(etree.tostring(docDefaults, pretty_print=True).decode())
else:
    print("No docDefaults found")

# Cek juga theme font size
body = doc.element.body
sectPr = body.find(qn("w:sectPr"))
if sectPr is not None:
    pgSz = sectPr.find(qn("w:pgSz"))
    pgMar = sectPr.find(qn("w:pgMar"))
    print(f"Page size: {pgSz.attrib if pgSz is not None else 'None'}")
    print(f"Page margin: {pgMar.attrib if pgMar is not None else 'None'}")