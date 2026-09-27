# Railway PostgreSQL to Google Drive Backup Service

এই সার্ভিসটি স্বয়ংক্রিয়ভাবে আপনার PostgreSQL ডেটাবেসের ব্যাকআপ নিয়ে সংকুচিত (`.sql.gz`) ফরম্যাটে গুগল ড্রাইভে আপলোড করবে।

---

## 🛠️ প্রয়োজনীয় Environment Variables (Railway-তে সেট করতে হবে)

| Variable | Description | উদাহরণ |
| :--- | :--- | :--- |
| `DATABASE_URL` | আপনার PostgreSQL কানেকশন স্ট্রিং | `postgresql://postgres:pass@roundhouse.proxy.rlwy.net:12345/railway` |
| `GDRIVE_FOLDER_ID` | গুগল ড্রাইভের ব্যাকআপ ফোল্ডারের ID | `1a2B3c4D5e...` (ফোল্ডারের URL থেকে পাওয়া যাবে) |
| `GDRIVE_SA_KEY` | গুগল সার্ভিস অ্যাকাউন্ট কী (সম্পূর্ণ JSON কন্টেন্ট) | `{"type": "service_account", "project_id": ...}` |
| `BACKUP_RETENTION_DAYS` *(ঐচ্ছিক)* | পুরনো ব্যাকআপ স্বয়ংক্রিয়ভাবে মুছে ফেলার দিন সংখ্যা (যেমন: 15 বা 30) | `30` (ডিফল্ট: `0` = কোনো ফাইল মুছবে না) |

---

## ⚠️ গুরুত্বপূর্ণ: গুগল ড্রাইভ পারমিশন সেটআপ
1. গুগল ক্লাউড কনসোল থেকে তৈরি করা **Service Account Email**-টি কপি করুন (যেমন: `backup-bot@my-project.iam.gserviceaccount.com`)।
2. গুগল ড্রাইভে যে ফোল্ডারে ব্যাকআপ রাখতে চান, সেই ফোল্ডারটির **Share** অপশনে যান।
3. সার্ভিস অ্যাকাউন্টের ইমেইলটি যোগ করে রোল দিন **Editor**।
*(শেয়ার না করলে গুগল ড্রাইভ API পারমিশন এরর দিবে।)*

---

## 🚀 Railway-তে Daily Backup হিসেবে সেটআপ করার নিয়ম

1. Railway-তে **New Service** তৈরি করে এই রিপোজিটরি ডিপ্লয় করুন।
2. সার্ভিসের **Variables** ট্যাবে গিয়ে উপরের Environment Variables গুলো যোগ করুন।
3. সার্ভিসের **Settings** ট্যাবে যান:
   - **Cron Schedule**: চালু করুন এবং এক্সপ্রেশন দিন: `0 2 * * *` (প্রতিদিন রাত ২টা UTC / বাংলাদেশ সময় সকাল ৮টা)।
   - **Restart Policy**: পরিবর্তন করে দিন **`On Failure`** অথবা **`Never`** (কখনই `Always` রাখবেন না, কারণ `Always` থাকলে ব্যাকআপ শেষ হওয়ার সাথে সাথে এটি আবার লুপে চলতে থাকবে)।
