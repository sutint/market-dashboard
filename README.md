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

## ข้อมูลกองทุนและทองไทย

Finnomena และสมาคมค้าทองคำบล็อก server ของ GitHub จึงให้คอมที่บ้านดึงแทน:
Task Scheduler ชื่อ **Market Dashboard - Thai data** รัน `run_fetch_thai.ps1` → `fetch_thai.py` ทุกวัน 08:30 และ 20:00
(ถ้าคอมปิดอยู่จะรันทันทีที่เปิดเครื่อง) สคริปต์จะ

1. ดึง NAV กองทุนตาม `portfolio.json` และราคาทองจากสมาคมฯ
2. เข้ารหัสแล้ว push เป็น `data/thai.enc.json` (กุญแจอยู่ใน `.thai_key` และ secret `THAI_DATA_KEY`)
3. อัปเดต secret `PORTFOLIO_JSON` จาก `portfolio.json` ในเครื่อง
4. สั่ง GitHub สร้างหน้าใหม่

log อยู่ที่ `logs/fetch_thai.log`

## รันในเครื่อง

```bash
pip install -r requirements.txt
python build.py
python -m http.server 8765 -d site
```

## แก้ไขพอร์ต

แก้ `portfolio.json` ในเครื่อง (หน่วย, ต้นทุน, ทอง, กองทุนสำรองเลี้ยงชีพในส่วน `manual`) แล้วรอรอบถัดไปของ Task Scheduler
หรืออยากให้ขึ้นทันที: คลิกขวาที่ task ใน Task Scheduler → Run

### กองทุนสำรองเลี้ยงชีพ (อัปเดตเองทุกเดือน)

ในส่วน `manual` ของ `portfolio.json` แก้ 4 ค่าตามรายงานจาก KAsset แล้วรอรอบถัดไป (หรือสั่ง Run task)

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
