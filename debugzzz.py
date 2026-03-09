from docx import Document
from docx.oxml.ns import qn

doc = Document("Technical_Spesification_Document_(TSD)_-_MPM_Dom_(CR46881).docx")
normal_style = doc.styles["Normal"]
pPr = normal_style.element.find(qn("w:pPr"))
rPr = normal_style.element.find(qn("w:rPr"))

# Cek spacing di style
if pPr is not None:
    spacing = pPr.find(qn("w:spacing"))
    print(f"Normal pPr spacing: {spacing.attrib if spacing is not None else 'None'}")
else:
    print("Normal pPr: None")

# Cek font size di style  
if rPr is not None:
    sz = rPr.find(qn("w:sz"))
    print(f"Normal font size (half-pts): {sz.get(qn('w:val')) if sz is not None else 'None'}")
else:
    print("Normal rPr: None")

# Cek default dari docDefaults
docDefaults = doc.element.find('.//' + qn("w:docDefaults"))
if docDefaults is not None:
    rPrDefault = docDefaults.find('.//' + qn("w:rPrDefault"))
    if rPrDefault is not None:
        sz = rPrDefault.find('.//' + qn("w:sz"))
        print(f"docDefault font size (half-pts): {sz.get(qn('w:val')) if sz is not None else 'None'}")
    pPrDefault = docDefaults.find('.//' + qn("w:pPrDefault"))
    if pPrDefault is not None:
        spacing = pPrDefault.find('.//' + qn("w:spacing"))
        print(f"docDefault spacing: {spacing.attrib if spacing is not None else 'None'}")