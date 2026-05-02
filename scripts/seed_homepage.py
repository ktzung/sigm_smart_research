#!/usr/bin/env python3
"""
Seed script: tạo dữ liệu mẫu cho Lab Homepage.
Tạo: 1 lab, admin user, 8 members (professor/phd/master/undergrad),
     profiles, publications, projects, 6 news items.

Usage:
    cd research_platform
    python scripts/seed_homepage.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date, timezone, timedelta
from app.core.database import init_db, SessionLocal
from app.core.security import hash_password
from app.models.auth import User
from app.models.lab import Lab, LabMember
from app.models.profile import UserProfile, Publication, Project, LabNews, LabEvent

_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)

MEMBERS = [
    # (email, display_name, password, role, title, bio, orcid, scholar_url, avatar_seed)
    (
        "admin@example.com", "Prof. Nguyen Van An", "password123",
        "professor",
        "Associate Professor, School of Information & Communication Technology",
        "Research interests: Federated Learning, Distributed AI, Privacy-Preserving ML. "
        "PI of the SigM Lab. 15+ years experience in machine learning research.",
        "0000-0002-1825-0097",
        "https://scholar.google.com/citations?user=example1",
        "NVA",
    ),
    (
        "tran.thi.bich@hust.edu.vn", "Dr. Tran Thi Bich", "password123",
        "professor",
        "Assistant Professor, AI & Data Science",
        "Specializes in Natural Language Processing, Large Language Models, and Knowledge Graphs. "
        "Co-PI of multiple national research projects.",
        "0000-0003-2345-6789",
        "https://scholar.google.com/citations?user=example2",
        "TTB",
    ),
    (
        "le.minh.duc@hust.edu.vn", "Le Minh Duc", "password123",
        "phd_student",
        "PhD Candidate — Federated Learning",
        "Researching concept drift adaptation in heterogeneous federated environments. "
        "Expected graduation: 2026.",
        "0000-0001-3456-7890",
        "https://scholar.google.com/citations?user=example3",
        "LMD",
    ),
    (
        "pham.thu.huong@hust.edu.vn", "Pham Thu Huong", "password123",
        "phd_student",
        "PhD Candidate — NLP & LLMs",
        "Working on Vietnamese language models and cross-lingual transfer learning. "
        "Published at ACL, EMNLP.",
        None,
        "https://scholar.google.com/citations?user=example4",
        "PTH",
    ),
    (
        "nguyen.quoc.hung@hust.edu.vn", "Nguyen Quoc Hung", "password123",
        "master_student",
        "MSc Student — Computer Vision",
        "Thesis: Real-time object detection for autonomous vehicles in Vietnamese traffic conditions.",
        None, None, "NQH",
    ),
    (
        "do.thi.lan@hust.edu.vn", "Do Thi Lan", "password123",
        "master_student",
        "MSc Student — Data Engineering",
        "Building scalable data pipelines for research data management. "
        "Interested in MLOps and reproducible research.",
        None, None, "DTL",
    ),
    (
        "hoang.van.minh@hust.edu.vn", "Hoang Van Minh", "password123",
        "undergraduate_student",
        "Undergraduate Researcher",
        "Final year student working on sentiment analysis for Vietnamese social media.",
        None, None, "HVM",
    ),
    (
        "vu.thi.nga@hust.edu.vn", "Vu Thi Nga", "password123",
        "undergraduate_student",
        "Undergraduate Researcher",
        "Exploring graph neural networks for citation network analysis.",
        None, None, "VTN",
    ),
]

PUBLICATIONS = {
    "admin@example.com": [
        {
            "title": "FedDrift: Adaptive Federated Learning under Concept Drift via Dynamic Clustering",
            "authors": ["Nguyen Van An", "Le Minh Duc", "Tran Thi Bich"],
            "venue": "IEEE Transactions on Neural Networks and Learning Systems",
            "year": 2024, "pub_type": "journal", "citation_count": 47,
            "doi": "10.1109/TNNLS.2024.001",
        },
        {
            "title": "Privacy-Preserving Federated Learning with Differential Privacy and Secure Aggregation",
            "authors": ["Nguyen Van An", "Pham Thu Huong"],
            "venue": "NeurIPS 2023",
            "year": 2023, "pub_type": "conference", "citation_count": 112,
        },
        {
            "title": "A Survey on Non-IID Data in Federated Learning: Challenges and Solutions",
            "authors": ["Nguyen Van An", "Le Minh Duc", "Do Thi Lan"],
            "venue": "ACM Computing Surveys",
            "year": 2023, "pub_type": "journal", "citation_count": 203,
        },
    ],
    "tran.thi.bich@hust.edu.vn": [
        {
            "title": "ViLLM: A Large Language Model for Vietnamese with Cultural Alignment",
            "authors": ["Tran Thi Bich", "Pham Thu Huong", "Nguyen Van An"],
            "venue": "ACL 2024",
            "year": 2024, "pub_type": "conference", "citation_count": 38,
        },
        {
            "title": "Knowledge Graph Completion for Vietnamese Biomedical Entities",
            "authors": ["Tran Thi Bich", "Pham Thu Huong"],
            "venue": "EMNLP 2023",
            "year": 2023, "pub_type": "conference", "citation_count": 29,
        },
    ],
    "le.minh.duc@hust.edu.vn": [
        {
            "title": "Detecting and Adapting to Concept Drift in Federated Learning with Minimal Communication",
            "authors": ["Le Minh Duc", "Nguyen Van An"],
            "venue": "ICML 2024 Workshop on Federated Learning",
            "year": 2024, "pub_type": "conference", "citation_count": 12,
        },
    ],
    "pham.thu.huong@hust.edu.vn": [
        {
            "title": "Cross-lingual Transfer for Low-Resource Vietnamese NLP Tasks",
            "authors": ["Pham Thu Huong", "Tran Thi Bich"],
            "venue": "EMNLP 2024",
            "year": 2024, "pub_type": "conference", "citation_count": 8,
        },
    ],
}

PROJECTS = {
    "admin@example.com": [
        {
            "title": "Federated Learning for Healthcare Data in Vietnam",
            "description": "Developing privacy-preserving FL frameworks for hospital networks across Vietnam, "
                           "enabling collaborative model training without sharing patient data.",
            "role": "Principal Investigator",
            "funding_source": "NAFOSTED Grant 102.05-2023.15",
            "start_date": date(2023, 1, 1),
            "end_date": date(2025, 12, 31),
            "status": "ongoing",
            "collaborators": ["Bach Mai Hospital", "Hanoi Medical University"],
        },
        {
            "title": "SigM Research Automation Platform",
            "description": "Building an AI-powered platform for automated systematic literature review, "
                           "from paper discovery to LaTeX export.",
            "role": "Lead Developer & PI",
            "funding_source": "HUST Internal Research Fund",
            "start_date": date(2024, 6, 1),
            "status": "ongoing",
            "collaborators": ["SigM Lab Members"],
        },
    ],
    "tran.thi.bich@hust.edu.vn": [
        {
            "title": "ViLLM: Vietnamese Large Language Model Development",
            "description": "Pre-training and fine-tuning large language models on Vietnamese corpora "
                           "with cultural and linguistic alignment.",
            "role": "Co-Principal Investigator",
            "funding_source": "Vietnam National University Grant",
            "start_date": date(2023, 6, 1),
            "status": "ongoing",
            "collaborators": ["VNU-HCM", "FPT AI Research"],
        },
    ],
}

NEWS_ITEMS = [
    {
        "title": "🏆 Best Paper Award at ICML 2024 Federated Learning Workshop",
        "content": (
            "We are thrilled to announce that our paper 'Detecting and Adapting to Concept Drift in "
            "Federated Learning with Minimal Communication' by Le Minh Duc and Prof. Nguyen Van An "
            "received the Best Paper Award at the ICML 2024 Workshop on Federated Learning. "
            "This work introduces a novel drift detection mechanism that reduces communication overhead "
            "by 60% while maintaining adaptation accuracy. Congratulations to the team!"
        ),
        "pinned": True,
        "published_at": _utcnow() - timedelta(days=3),
    },
    {
        "title": "📢 SigM Research Automation Platform v2.0 Released",
        "content": (
            "We are excited to release version 2.0 of our Research Automation Platform — "
            "an AI-powered tool for systematic literature reviews. New features include: "
            "multi-model routing (Claude Opus, Gemini Pro, GPT-4o), 15-stage pipeline, "
            "GitHub code integration, and automated LaTeX export. "
            "The platform is now available for all HUST researchers. Contact us for access."
        ),
        "pinned": True,
        "published_at": _utcnow() - timedelta(days=7),
    },
    {
        "title": "🎓 PhD Position Available: Federated Learning & Privacy",
        "content": (
            "The SigM Lab is recruiting 2 PhD students for the 2025 intake. "
            "Research topics: (1) Federated Learning under Distribution Shift, "
            "(2) Privacy-Preserving Machine Learning for Healthcare. "
            "Requirements: Strong background in ML/DL, Python proficiency, "
            "English B2+. Full scholarship available. "
            "Application deadline: March 31, 2025. Send CV to sigm@hust.edu.vn."
        ),
        "pinned": False,
        "published_at": _utcnow() - timedelta(days=14),
    },
    {
        "title": "📄 Two Papers Accepted at ACL 2024",
        "content": (
            "Congratulations to Dr. Tran Thi Bich and Pham Thu Huong! "
            "Their paper 'ViLLM: A Large Language Model for Vietnamese with Cultural Alignment' "
            "has been accepted at ACL 2024 (Main Conference). "
            "Additionally, 'Cross-lingual Transfer for Low-Resource Vietnamese NLP Tasks' "
            "was accepted at EMNLP 2024. Great achievements for the lab!"
        ),
        "pinned": False,
        "published_at": _utcnow() - timedelta(days=21),
    },
    {
        "title": "🤝 New Collaboration with Bach Mai Hospital",
        "content": (
            "SigM Lab has signed a research collaboration agreement with Bach Mai Hospital "
            "to develop federated learning solutions for medical imaging analysis. "
            "This 3-year project (2024-2026) will focus on privacy-preserving AI for "
            "radiology and pathology, funded by NAFOSTED. "
            "We welcome medical informatics researchers to join this initiative."
        ),
        "pinned": False,
        "published_at": _utcnow() - timedelta(days=35),
    },
    {
        "title": "🏫 SigM Lab Open Day — Visit Us!",
        "content": (
            "Join us for the SigM Lab Open Day on the last Friday of each month. "
            "Current and prospective students, industry partners, and researchers are welcome. "
            "We will present ongoing projects, demo the Research Automation Platform, "
            "and discuss collaboration opportunities. "
            "Location: Room B1-302, School of ICT, HUST. Time: 14:00-17:00."
        ),
        "pinned": False,
        "published_at": _utcnow() - timedelta(days=45),
    },
]


def seed():
    init_db()
    db = SessionLocal()

    try:
        # ── Create or get users ───────────────────────────────────────────────
        users: dict[str, User] = {}
        for email, display_name, password, role_in_lab, title, bio, orcid, scholar, _ in MEMBERS:
            user = db.query(User).filter_by(email=email).first()
            if not user:
                user = User(
                    email=email,
                    display_name=display_name,
                    password_hash=hash_password(password),
                    role="admin" if email == "admin@example.com" else "user",
                    plan="paid" if role_in_lab in ("professor", "phd_student") else "free",
                )
                db.add(user)
                db.flush()
                print(f"  ✓ Created user: {display_name} ({email})")
            else:
                print(f"  · Existing user: {display_name}")
            users[email] = user

            # Profile
            profile = db.query(UserProfile).filter_by(user_id=user.id).first()
            if not profile:
                profile = UserProfile(
                    user_id=user.id,
                    title=title,
                    bio=bio,
                    orcid=orcid,
                    google_scholar_url=scholar,
                    avatar_url=None,
                )
                db.add(profile)
            else:
                profile.title = title
                profile.bio = bio
                profile.orcid = orcid
                profile.google_scholar_url = scholar

        db.flush()

        # ── Create or get lab ─────────────────────────────────────────────────
        admin_user = users["admin@example.com"]
        lab = db.query(Lab).filter_by(owner_id=admin_user.id).first()
        if not lab:
            lab = Lab(
                name="SigM Lab — Signal & Machine Intelligence",
                description=(
                    "The SigM Lab at HUST focuses on Federated Learning, Privacy-Preserving AI, "
                    "Natural Language Processing, and Research Automation. "
                    "We develop AI systems that are robust, private, and deployable in real-world settings."
                ),
                owner_id=admin_user.id,
            )
            db.add(lab)
            db.flush()
            print(f"  ✓ Created lab: {lab.name} (id={lab.id})")
        else:
            print(f"  · Existing lab: {lab.name} (id={lab.id})")

        # ── Add lab members ───────────────────────────────────────────────────
        for email, _, _, lab_role, _, _, _, _, _ in MEMBERS:
            user = users[email]
            existing = db.query(LabMember).filter_by(lab_id=lab.id, user_id=user.id).first()
            if not existing:
                db.add(LabMember(lab_id=lab.id, user_id=user.id, role=lab_role))
                print(f"  ✓ Added member: {user.display_name} as {lab_role}")

        db.flush()

        # ── Publications ──────────────────────────────────────────────────────
        for email, pubs in PUBLICATIONS.items():
            user = users[email]
            existing_count = db.query(Publication).filter_by(user_id=user.id).count()
            if existing_count == 0:
                for pub in pubs:
                    db.add(Publication(
                        user_id=user.id,
                        title=pub["title"],
                        authors=pub["authors"],
                        venue=pub["venue"],
                        year=pub["year"],
                        pub_type=pub["pub_type"],
                        citation_count=pub.get("citation_count", 0),
                        doi=pub.get("doi"),
                    ))
                print(f"  ✓ Added {len(pubs)} publications for {email}")

        # ── Projects ──────────────────────────────────────────────────────────
        for email, projs in PROJECTS.items():
            user = users[email]
            existing_count = db.query(Project).filter_by(user_id=user.id).count()
            if existing_count == 0:
                for proj in projs:
                    db.add(Project(
                        user_id=user.id,
                        title=proj["title"],
                        description=proj["description"],
                        role=proj["role"],
                        funding_source=proj.get("funding_source"),
                        start_date=proj["start_date"],
                        end_date=proj.get("end_date"),
                        status=proj["status"],
                        collaborators=proj.get("collaborators", []),
                    ))
                print(f"  ✓ Added {len(projs)} projects for {email}")

        # ── News ──────────────────────────────────────────────────────────────
        existing_news = db.query(LabNews).filter_by(lab_id=lab.id).count()
        if existing_news == 0:
            for item in NEWS_ITEMS:
                db.add(LabNews(
                    lab_id=lab.id,
                    author_id=admin_user.id,
                    title=item["title"],
                    content=item["content"],
                    pinned=item["pinned"],
                    published_at=item["published_at"],
                ))
            print(f"  ✓ Added {len(NEWS_ITEMS)} news items")

        # ── Events ───────────────────────────────────────────────────────────
        existing_events = db.query(LabEvent).filter_by(lab_id=lab.id).count()
        if existing_events == 0:
            events_data = [
                {
                    "title": "SigM Lab Weekly Seminar: Federated Learning Updates",
                    "description": "Weekly research seminar. This week: Le Minh Duc presents progress on concept drift detection in FL. All lab members and guests welcome.",
                    "event_date": _utcnow() + timedelta(days=3),
                    "location": "Room B1-302, School of ICT, HUST",
                    "event_type": "seminar",
                    "url": None,
                },
                {
                    "title": "PhD Defense: Pham Thu Huong — ViLLM Cross-lingual Transfer",
                    "description": "PhD thesis defense by Pham Thu Huong. Topic: Cross-lingual Transfer Learning for Low-Resource Vietnamese NLP. Committee members from HUST, VNU-HCM, and FPT AI.",
                    "event_date": _utcnow() + timedelta(days=12),
                    "location": "Hall C2-101, HUST",
                    "event_type": "defense",
                    "url": None,
                },
                {
                    "title": "Workshop: AI for Healthcare — Privacy & Federated Learning",
                    "description": "Half-day workshop co-organized with Bach Mai Hospital. Topics: federated learning in clinical settings, differential privacy, regulatory compliance. Registration required.",
                    "event_date": _utcnow() + timedelta(days=21),
                    "location": "Bach Mai Hospital, Conference Room A",
                    "event_type": "workshop",
                    "url": "https://sigm.hust.edu.vn/events/ai-healthcare-2025",
                },
                {
                    "title": "Paper Submission Deadline — NeurIPS 2025",
                    "description": "Abstract deadline for NeurIPS 2025. All lab members targeting this venue should have drafts ready for internal review 2 weeks prior.",
                    "event_date": _utcnow() + timedelta(days=35),
                    "location": "Online",
                    "event_type": "deadline",
                    "url": "https://neurips.cc/Conferences/2025",
                },
                {
                    "title": "ICML 2025 — Lab Attendance",
                    "description": "Prof. Nguyen Van An and Le Minh Duc will attend ICML 2025 in Vienna. Paper presentation: FedDrift v2. Contact PI for meeting scheduling.",
                    "event_date": _utcnow() + timedelta(days=58),
                    "location": "Vienna, Austria",
                    "event_type": "conference",
                    "url": "https://icml.cc/Conferences/2025",
                },
            ]
            for ev in events_data:
                db.add(LabEvent(
                    lab_id=lab.id,
                    author_id=admin_user.id,
                    **ev,
                ))
            print(f"  ✓ Added {len(events_data)} events")

        db.commit()

        print(f"\n✅ Seed complete!")
        print(f"   Lab ID: {lab.id}  (set localStorage public_lab_id={lab.id} in browser)")
        print(f"   Admin login: admin@example.com / password123")
        print(f"   Members: {len(MEMBERS)} | News: {len(NEWS_ITEMS)}")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("🌱 Seeding homepage data...\n")
    seed()
