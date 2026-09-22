import requests
from datetime import datetime

from database import SessionLocal, Base, engine
from models import Job


API_URL = "https://api.jobopportunitiesapi.org/public/jobs"


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def get_first(data, *keys):
    for key in keys:
        value = data.get(key)

        if value is not None and str(value).strip():
            return value

    return None


def infer_qualification(text):
    text = clean_text(text).lower()

    if "ph.d" in text or "phd" in text:
        return "PhD"

    if "post graduate" in text or "postgraduate" in text or "master" in text:
        return "PG"

    if (
        "bachelor" in text
        or "b.tech" in text
        or "b.e." in text
        or "degree" in text
        or "graduate" in text
        or "undergraduate" in text
    ):
        return "UG"

    if "diploma" in text:
        return "Diploma"

    if "iti" in text:
        return "ITI"

    if "12th" in text or "hsc" in text or "higher secondary" in text:
        return "12th"

    if "10th" in text or "sslc" in text or "secondary school" in text:
        return "10th"

    return "Any"


def infer_category(title, description):
    text = (
        clean_text(title) + " " +
        clean_text(description)
    ).lower()

    categories = [
        ("software", "IT / Software"),
        ("developer", "IT / Software"),
        ("programmer", "IT / Software"),
        ("data analyst", "Data / Analytics"),
        ("data scientist", "Data / Analytics"),
        ("accountant", "Finance / Accounting"),
        ("finance", "Finance / Accounting"),
        ("sales", "Sales"),
        ("marketing", "Marketing"),
        ("teacher", "Teaching / Education"),
        ("school", "Teaching / Education"),
        ("nurse", "Healthcare"),
        ("doctor", "Healthcare"),
        ("driver", "Driver"),
        ("electrician", "Electrician"),
        ("plumber", "Plumber"),
        ("painter", "Painter"),
        ("construction", "Construction"),
        ("catering", "Catering"),
        ("hotel", "Hotel / Hospitality"),
        ("hospitality", "Hotel / Hospitality"),
        ("security", "Security"),
        ("housekeeping", "Housekeeping"),
        ("delivery", "Delivery"),
        ("mechanic", "Mechanic"),
        ("factory", "Factory"),
        ("warehouse", "Warehouse"),
        ("admin", "Office / Admin"),
        ("office", "Office / Admin"),
    ]

    for keyword, category in categories:
        if keyword in text:
            return category

    return "Other"


def infer_skills(title, description):
    text = (
        clean_text(title) + " " +
        clean_text(description)
    ).lower()

    possible_skills = [
        "python",
        "java",
        "javascript",
        "react",
        "sql",
        "excel",
        "ms office",
        "communication",
        "sales",
        "marketing",
        "customer service",
        "driving",
        "electrical",
        "welding",
        "plumbing",
        "cooking",
        "catering",
        "security",
        "housekeeping",
        "data entry",
        "accounting",
        "tally",
        "mechanical",
        "machine operation",
        "warehouse",
        "logistics",
        "teaching",
    ]

    found = []

    for skill in possible_skills:
        if skill in text:
            found.append(skill)

    if found:
        return ", ".join(found)

    return clean_text(title) or "General skills"


def parse_date(value):
    if not value:
        return None

    value = clean_text(value)

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%d-%m-%Y",
        "%d/%m/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None


def load_real_jobs():
    print("Connecting to live job source...")
    print(API_URL)

    try:
        response = requests.get(
            API_URL,
            params={
                "country": "IN",
                "limit": 50,
                "include_description": "true"
            },
            timeout=30
        )

        response.raise_for_status()

    except requests.RequestException as error:
        print("Could not connect to live job source.")
        print("Error:", error)
        return


    try:
        data = response.json()
    except ValueError:
        print("The job source returned invalid JSON.")
        return


    # Support common API response formats.
    if isinstance(data, list):
        jobs_data = data

    elif isinstance(data, dict):
        jobs_data = (
            data.get("jobs")
            or data.get("results")
            or data.get("data")
            or []
        )

    else:
        jobs_data = []


    if not isinstance(jobs_data, list):
        jobs_data = []


    print("Total jobs received :", len(jobs_data))


    # Make sure tables exist.
    Base.metadata.create_all(bind=engine)


    db = SessionLocal()

    added = 0
    updated = 0
    skipped = 0


    try:

        for item in jobs_data:

            if not isinstance(item, dict):
                skipped += 1
                continue


            title = clean_text(
                get_first(
                    item,
                    "title",
                    "job_title",
                    "name",
                )
            )


            if not title:
                skipped += 1
                continue


            company = clean_text(
                get_first(
                    item,
                    "company",
                    "company_name",
                    "organization",
                    "employer",
                )
            )


            description = clean_text(
                get_first(
                    item,
                    "description",
                    "job_description",
                    "details",
                )
            )


            category = clean_text(
                get_first(
                    item,
                    "category",
                    "job_category",
                )
            )


            if not category:
                category = infer_category(
                    title,
                    description
                )


            state = clean_text(
                get_first(
                    item,
                    "state",
                    "state_name",
                )
            )


            district = clean_text(
                get_first(
                    item,
                    "district",
                    "district_name",
                )
            )


            city = clean_text(
                get_first(
                    item,
                    "city",
                    "city_name",
                    "location",
                )
            )


            job_type = clean_text(
                get_first(
                    item,
                    "job_type",
                    "employment_type",
                    "type",
                )
            )


            qualification = clean_text(
                get_first(
                    item,
                    "qualification",
                    "education",
                    "education_level",
                )
            )


            if not qualification:
                qualification = infer_qualification(
                    title + " " + description
                )


            skills = clean_text(
                get_first(
                    item,
                    "skills",
                    "required_skills",
                )
            )


            if not skills:
                skills = infer_skills(
                    title,
                    description
                )


            experience = clean_text(
                get_first(
                    item,
                    "experience",
                    "experience_required",
                )
            )


            salary = clean_text(
                get_first(
                    item,
                    "salary",
                    "salary_range",
                    "pay",
                )
            )


            vacancy = get_first(
                item,
                "vacancy_count",
                "vacancies",
                "number_of_vacancies",
                "positions",
            )


            try:
                vacancy = int(vacancy) if vacancy else 1
            except (TypeError, ValueError):
                vacancy = 1


            deadline_raw = get_first(
                item,
                "deadline",
                "last_date",
                "closing_date",
                "application_deadline",
            )


            deadline = parse_date(
                deadline_raw
            )


            source_url = clean_text(
                get_first(
                    item,
                    "apply_url",
                    "application_url",
                    "url",
                    "source_url",
                    "job_url",
                )
            )


            source_id = clean_text(
                get_first(
                    item,
                    "id",
                    "job_id",
                    "external_id",
                )
            )


            # Use source URL as the primary duplicate key.
            existing = None


            if source_url:

                existing = (
                    db.query(Job)
                    .filter(
                        Job.source_url == source_url
                    )
                    .first()
                )


            # Fallback duplicate check when URL is missing.
            if existing is None:

                existing = (
                    db.query(Job)
                    .filter(
                        Job.title == title,
                        Job.company == company,
                        Job.city == city
                    )
                    .first()
                )


            if existing:

                existing.title = title
                existing.company = company
                existing.category = category
                existing.job_type = job_type or existing.job_type
                existing.state = state or existing.state
                existing.district = district or existing.district
                existing.city = city or existing.city
                existing.description = description
                existing.qualification = qualification
                existing.skills = skills
                existing.experience = experience
                existing.salary = salary
                existing.vacancy_count = vacancy
                existing.deadline = deadline
                existing.source = "Live Job Source"
                existing.source_url = source_url or existing.source_url
                existing.is_active = True

                updated += 1

            else:

                job = Job(

                    title=title,

                    company=company or "Company not specified",

                    category=category,

                    job_type=job_type or "Not specified",

                    state=state or "India",

                    district=district or None,

                    city=city or None,

                    description=description or "No description available.",

                    qualification=qualification,

                    skills=skills,

                    experience=experience or None,

                    salary=salary or None,

                    vacancy_count=vacancy,

                    deadline=deadline,

                    source="Live Job Source",

                    source_url=source_url or None,

                    employer_id=None,

                    is_active=True,

                )


                db.add(job)
                added += 1


        db.commit()


    except Exception as error:

        db.rollback()

        print("Database update failed.")
        print("Error:", error)

        return

    finally:

        db.close()


    print()
    print("===================================")
    print("CareerConnect Real Jobs Sync")
    print("===================================")
    print("New jobs added :", added)
    print("Jobs updated   :", updated)
    print("Skipped        :", skipped)
    print("Total received :", len(jobs_data))
    print("===================================")


if __name__ == "__main__":
    load_real_jobs()