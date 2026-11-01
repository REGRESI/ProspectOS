"""Generate fictional 773-row CleanStar-shaped CSV to stdout, never real PII."""

import csv
import sys

HEADERS = [
    "First Name",
    "Last Name",
    "Company Name",
    "Job title",
    "Email",
    "Email deliverability",
    "Phone",
    "Gender",
    "Company Location",
    "Company domain",
    "Linkedin Profile Url",
    "Linkedin Company Url",
    "Open?",
    "Premium?",
]


def generate(output, count=773):
    writer = csv.DictWriter(output, fieldnames=HEADERS)
    writer.writeheader()
    for i in range(count):
        writer.writerow(
            {
                "First Name": f"Demo{i + 1}",
                "Last Name": "Synthetisch",
                "Company Name": f"Demo Büro {i // 4 + 1}" if i else "",
                "Job title": "Office Management" if i else "",
                "Company Location": "Offenburg",
                "Linkedin Profile Url": f"https://www.linkedin.com/in/prospectos-fictional-{i + 1}",
                "Linkedin Company Url": f"https://www.linkedin.com/company/prospectos-fictional-{i // 4 + 1}",
                "Open?": "",
                "Premium?": "",
            }
        )


if __name__ == "__main__":
    generate(sys.stdout)
