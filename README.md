# Market Dashboard

แดชบอร์ดข้อมูลการลงทุนส่วนตัว อัปเดตอัตโนมัติวันละ 2 รอบ (07:00 และ 18:30 น.) ผ่าน GitHub Actions แล้วเผยแพร่บน GitHub Pages
ข้อมูลทั้งหน้าถูกเข้ารหัส (AES-GCM) ต้องใส่รหัสผ่านก่อนเปิดดู

| ไฟล์ | หน้าที่ |
|---|---|
| `config.json` | รายการดัชนี / สินค้าโภคภัณฑ์ / คริปโต / หุ้นที่ติดตาม (ใช้ symbol ของ Yahoo Finance; หุ้นไทยต่อท้าย `.BK`) |
| `portfolio.json` | พอร์ตกองทุน (ไม่ถูก commit — อยู่ใน GitHub Secret `PORTFOLIO_JSON`) |
| `build.py` | ดึงข้อมูลแล้วสร้าง `site/index.html` |
| `template.html` | หน้าตา dashboard |
| `data/snapshots.json` | เก็บราคาปิดรายวันของดัชนีที่ Yahoo ไม่มีประวัติ (SET, SET50, CSI 300, VN-Index) |

## รันในเครื่อง

```bash
pip install -r requirements.txt
python build.py
python -m http.server 8765 -d site
```

## แก้ไขพอร์ต

1. แก้ `portfolio.json` (เพิ่ม/ลดหน่วย, ต้นทุน, NAV ของกองทุนสำรองเลี้ยงชีพในส่วน `manual`)
2. อัปเดต secret: `gh secret set PORTFOLIO_JSON < portfolio.json`
3. สั่งรันทันที: `gh workflow run daily.yml`

### กองทุนสำรองเลี้ยงชีพ (อัปเดตเองทุกเดือน)

ในส่วน `manual` ของ `portfolio.json` แก้ 4 ค่าตามรายงานจาก KAsset แล้วทำข้อ 2–3 ด้านบน

```json
"units": 170187.287,        // จำนวนหน่วยทั้งหมด
"cost_total": 2714616,      // ต้นทุนรวม (บาท)
"nav": 16.5861,             // NAV ต่อหน่วย
"nav_date": "2026-10-09"    // วันที่ของ NAV
```

## เปลี่ยนรหัสผ่าน

```bash
gh secret set DASHBOARD_PASSWORD
```
