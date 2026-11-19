from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
wb=Workbook(); ws=wb.active; ws.title="Order list"
ws["A1"]="Pemberton Georgetown: front living room order list"; ws["A1"].font=Font(bold=True,size=14)
ws["A2"]="Prices from the Notion order list (Maison Verde pricing effective Oct 19). Prepared Oct 26, 2026. Draft for Jessica's review only."
ws["A2"].font=Font(italic=True,size=9)
hdr=["Vendor","Item","Spec","Qty","Unit","Unit price","Line total","Claire's sign-off (line ≥ $400)","Notes"]
ws.append([]); ws.append(hdr)
H=4
for c in ws[H]: c.font=Font(bold=True,color="FFFFFF"); c.fill=PatternFill("solid",fgColor="5B5346"); c.alignment=Alignment(wrap_text=True,vertical="center")
rows=[
("Maison Verde Trade","Hollis sofa, COM, 108 in","108 in: longest standard length within the 148 in (12' 4\") laser measure less 18 in clear at each end",1,"ea",4520,"COM fabric: the Halden line below"),
("Loom and Field Textiles","Halden performance linen, Cashew 7214 (COM for Hollis)","54 in plain; 18 yd per the Hollis COM chart at 108 in",18,"yd",86,"Colourway subject to Claire confirming Cashew 7214 by tag name and number. Passes ACT high traffic (38,000 double rubs Wyzenbeek against 30,000). Before ordering: CFA from the current dye lot, and the mill card showing one lot covering all 18 yd"),
("Maison Verde Trade","Pike coffee table, white oak, 54 in","",1,"ea",1180,"Price from Oct 19"),
("Maison Verde Trade","Arlo side table, white oak","",2,"ea",365,"Price from Oct 19. Unit under $400, but the line is over it"),
("Maison Verde Trade","Wren table lamp, satin brass","",2,"ea",186,""),
("Maison Verde Trade","Flatweave wool rug, oatmeal, 8 x 10 ft","",1,"ea",612,""),
("Loom and Field Textiles","Linen sheers, ivory, pair of panels","Pair, for the front window",2,"ea",152,"Sample S-205. Width of 72 in is taken from drawing EX-1 (June 2025), not a site measurement. Laser-measure the window before ordering"),
("Loom and Field Textiles","Boucle pillows, oatmeal, 22 in","",4,"ea",64,""),
]
r0=H+1
for i,(v,it,sp,q,u,p,n) in enumerate(rows):
    r=r0+i
    ws.append([v,it,sp,q,u,p,f"=D{r}*F{r}",f'=IF(G{r}>=400,"Yes","No")',n])
last=r0+len(rows)-1
t=last+2
ws.cell(t,6,"Grand total").font=Font(bold=True)
ws.cell(t,7,f"=SUM(G{r0}:G{last})").font=Font(bold=True)
ws.cell(t+1,6,"Lines needing sign-off")
ws.cell(t+1,7,f'=SUMIF(H{r0}:H{last},"Yes",G{r0}:G{last})')
ws.cell(t+3,1,"Rule (Studio standards): any line of $400 or more needs Claire's written sign-off before Priya orders it, and Jessica's approval as well.").font=Font(italic=True,size=9)
thin=Side(style="thin",color="BBBBBB")
for row in ws.iter_rows(min_row=H,max_row=last,max_col=9):
    for c in row: c.border=Border(top=thin,bottom=thin,left=thin,right=thin); c.alignment=Alignment(wrap_text=True,vertical="top")
for r in range(r0,t+2):
    for col in (6,7): ws.cell(r,col).number_format='$#,##0.00'
for col,w in zip("ABCDEFGHI",[22,36,34,6,6,12,13,16,52]): ws.column_dimensions[col].width=w
ws.freeze_panes="A5"
wb.save("pemberton_living_room_order.xlsx")
