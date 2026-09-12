import re

SKILLS = {
    "python": ["python"], "java": ["java"], "javascript": ["javascript", "js"],
    "typescript": ["typescript", "ts"], "react": ["react", "react.js", "reactjs"],
    "next.js": ["next.js", "nextjs"], "angular": ["angular"], "vue": ["vue", "vue.js"],
    "node.js": ["node.js", "nodejs", "node"], "fastapi": ["fastapi"], "django": ["django"],
    "flask": ["flask"], "spring boot": ["spring boot"], "rest": ["rest", "rest api", "restful"],
    "graphql": ["graphql"], "sql": ["sql"], "postgresql": ["postgresql", "postgres"],
    "mysql": ["mysql"], "oracle": ["oracle"], "mongodb": ["mongodb", "mongo"],
    "redis": ["redis"], "snowflake": ["snowflake"], "bigquery": ["bigquery"],
    "aws": ["aws", "amazon web services"], "azure": ["azure"], "gcp": ["gcp", "google cloud"],
    "docker": ["docker"], "kubernetes": ["kubernetes", "k8s"], "terraform": ["terraform"],
    "git": ["git"], "github": ["github"], "jenkins": ["jenkins"], "github actions": ["github actions"],
    "machine learning": ["machine learning", "ml"], "deep learning": ["deep learning"],
    "nlp": ["nlp", "natural language processing"], "pandas": ["pandas"], "numpy": ["numpy"],
    "scikit-learn": ["scikit-learn", "sklearn"], "tensorflow": ["tensorflow"], "pytorch": ["pytorch"],
    "spark": ["spark", "apache spark"], "tableau": ["tableau"], "power bi": ["power bi"],
    "oic": ["oic", "oracle integration cloud"], "hcm extracts": ["hcm extracts", "hcm extract"],
    "bi publisher": ["bi publisher", "bip"], "otbi": ["otbi"], "hdl": ["hdl", "hcm data loader"],
}

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()

def extract_skills(text: str) -> list[str]:
    t = normalize(text)
    found = []
    for canonical, aliases in SKILLS.items():
        for alias in aliases:
            if re.search(r"(?<![\w])" + re.escape(alias.lower()) + r"(?![\w])", t):
                found.append(canonical)
                break
    return sorted(set(found))
