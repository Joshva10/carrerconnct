from database import SessionLocal
from models import GovernmentJob
from datetime import datetime


# Official government recruitment / examination notifications
# Sources are official government websites.
GOVERNMENT_JOBS = [
    {
        "title": "Combined Geo-Scientist (Preliminary) Examination, 2027",
        "organization": "Union Public Service Commission (UPSC)",
        "state": "All India",
        "qualification": "See official notification",
        "description": (
            "UPSC examination notification for the Combined Geo-Scientist "
            "Preliminary Examination, 2027. Candidates should check the "
            "official UPSC notification for eligibility, syllabus, dates "
            "and application instructions."
        ),
        "exam_date": None,
        "last_date": None,
        "notification_url": "https://www.upsc.gov.in/",
        "source": "UPSC Official",
        "is_active": True,
    },
    {
        "title": "Advertisement No. 52 - 2026 (Special)",
        "organization": "Union Public Service Commission (UPSC)",
        "state": "All India",
        "qualification": "See official notification",
        "description": (
            "Special recruitment advertisement published by UPSC. "
            "Check the official recruitment advertisement for post-wise "
            "eligibility, vacancies, dates and application instructions."
        ),
        "exam_date": None,
        "last_date": None,
        "notification_url": "https://www.upsc.gov.in/recruitment/recruitment-advertisement",
        "source": "UPSC Official",
        "is_active": True,
    },
    {
        "title": "Advertisement No. 10 - 2026",
        "organization": "Union Public Service Commission (UPSC)",
        "state": "All India",
        "qualification": "See official notification",
        "description": (
            "UPSC recruitment advertisement. Candidates must refer to "
            "the official notification for post details, eligibility, "
            "vacancies, important dates and application procedure."
        ),
        "exam_date": None,
        "last_date": None,
        "notification_url": "https://www.upsc.gov.in/recruitment/recruitment-advertisement",
        "source": "UPSC Official",
        "is_active": True,
    },
    {
        "title": "Scientist-B (Instrumentation) - Ministry of Earth Sciences",
        "organization": "Union Public Service Commission (UPSC)",
        "state": "All India",
        "qualification": "See official notification",
        "description": (
            "UPSC recruitment notice for Scientist-B (Instrumentation) "
            "posts in the Ministry of Earth Sciences. Check the official "
            "notice for eligibility and application details."
        ),
        "exam_date": None,
        "last_date": None,
        "notification_url": "https://www.upsc.gov.in/recruitment/recruitment-test/notices",
        "source": "UPSC Official",
        "is_active": True,
    },
    {
        "title": "Scientist-B (General Meteorology) - Ministry of Earth Sciences",
        "organization": "Union Public Service Commission (UPSC)",
        "state": "All India",
        "qualification": "See official notification",
        "description": (
            "UPSC recruitment notice for Scientist-B (General Meteorology) "
            "posts in the Ministry of Earth Sciences. Check the official "
            "notice for eligibility and application details."
        ),
        "exam_date": None,
        "last_date": None,
        "notification_url": "https://www.upsc.gov.in/recruitment/recruitment-test/notices",
        "source": "UPSC Official",
        "is_active": True,
    },
    {
        "title": "Assistant Director Grade-II (IEDS) - Leather & Footwear",
        "organization": "Union Public Service Commission (UPSC)",
        "state": "All India",
        "qualification": "See official notification",
        "description": (
            "UPSC recruitment notice for Assistant Director Grade-II "
            "(IEDS) - Leather & Footwear in the Ministry of MSME. "
            "Check the official notice for complete eligibility details."
        ),
        "exam_date": None,
        "last_date": None,
        "notification_url": "https://www.upsc.gov.in/recruitment/recruitment-test/notices",
        "source": "UPSC Official",
        "is_active": True,
    },
    {
        "title": "Assistant Director Grade-II (IEDS) - Food",
        "organization": "Union Public Service Commission (UPSC)",
        "state": "All India",
        "qualification": "See official notification",
        "description": (
            "UPSC recruitment notice for Assistant Director Grade-II "
            "(IEDS) - Food in the Ministry of MSME. Check the official "
            "notice for complete eligibility details."
        ),
        "exam_date": None,
        "last_date": None,
        "notification_url": "https://www.upsc.gov.in/recruitment/recruitment-test/notices",
        "source": "UPSC Official",
        "is_active": True,
    },
]


def load_government_jobs():
    db = SessionLocal()

    added = 0
    skipped = 0

    try:
        for item in GOVERNMENT_JOBS:

            existing = (
                db.query(GovernmentJob)
                .filter(
                    GovernmentJob.title == item["title"],
                    GovernmentJob.organization == item["organization"]
                )
                .first()
            )

            if existing:
                skipped += 1
                continue

            job = GovernmentJob(
                title=item["title"],
                organization=item["organization"],
                state=item["state"],
                qualification=item["qualification"],
                description=item["description"],
                exam_date=item["exam_date"],
                last_date=item["last_date"],
                notification_url=item["notification_url"],
                source=item["source"],
                is_active=item["is_active"],
                created_at=datetime.utcnow()
            )

            db.add(job)
            added += 1

        db.commit()

        print()
        print("=" * 55)
        print("CareerConnect Government Jobs Loader")
        print("=" * 55)
        print(f"New government jobs added : {added}")
        print(f"Already existing/skipped  : {skipped}")
        print(f"Total records in this file: {len(GOVERNMENT_JOBS)}")
        print("=" * 55)
        print()
        print("Government jobs loaded successfully!")

    except Exception as e:
        db.rollback()
        print()
        print("ERROR while loading government jobs:")
        print(e)

    finally:
        db.close()


if __name__ == "__main__":
    load_government_jobs()