"""
scripts/seed_vector_db.py
─────────────────────────
Run once (or when you need to refresh the vector store):

    python -m scripts.seed_vector_db

Seeds two ChromaDB collections with a clinically representative set of:
  - ICD-10 diagnosis codes (100 core entries across major categories)
  - CPT procedure codes  (60 core entries across major specialties)

The Coder Agent uses cosine similarity against these to propose
valid, existing alphanumeric healthcare codes — NO weight fine-tuning.
"""
import sys
import os

# Allow running from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.vector_store import get_icd10_collection, get_cpt_collection
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ── ICD-10 Seed Data ─────────────────────────────────────────────────────────
# Format: (code, clinical_description_used_for_embedding)
ICD10_SEED: list[tuple[str, str]] = [
    # Digestive System
    ("K35.80", "acute appendicitis without abscess or peritonitis"),
    ("K35.20", "acute appendicitis with generalized peritonitis"),
    ("K80.20", "calculus of gallbladder without cholecystitis"),
    ("K70.30", "alcoholic cirrhosis of liver without ascites"),
    ("K92.1",  "melena lower gastrointestinal bleed"),
    ("K57.30", "diverticulosis of large intestine without perforation or abscess"),
    ("K25.9",  "gastric ulcer unspecified as acute or chronic"),
    ("K21.0",  "gastro-esophageal reflux disease with esophagitis"),
    ("K51.90", "ulcerative colitis unspecified without complications"),
    ("K50.90", "Crohn disease of small intestine without complications"),
    # Cardiovascular
    ("I21.9",  "acute myocardial infarction unspecified ST elevation"),
    ("I50.9",  "heart failure unspecified congestive cardiac failure"),
    ("I10",    "essential primary hypertension high blood pressure"),
    ("I48.0",  "paroxysmal atrial fibrillation cardiac arrhythmia"),
    ("I63.9",  "cerebral infarction unspecified ischemic stroke"),
    ("I25.10", "atherosclerotic heart disease of native coronary artery"),
    ("I34.0",  "nonrheumatic mitral valve regurgitation insufficiency"),
    ("I47.1",  "supraventricular tachycardia SVT rapid heart rate"),
    ("I82.401","acute deep vein thrombosis DVT unspecified femoral vein"),
    ("I26.99", "other pulmonary embolism without acute cor pulmonale"),
    # Respiratory
    ("J18.9",  "pneumonia unspecified organism community acquired"),
    ("J44.1",  "chronic obstructive pulmonary disease COPD exacerbation"),
    ("J45.901","unspecified asthma with acute exacerbation bronchospasm"),
    ("J06.9",  "acute upper respiratory infection unspecified common cold"),
    ("J20.9",  "acute bronchitis unspecified"),
    ("J96.00", "acute respiratory failure unspecified whether with hypoxia"),
    ("J12.82", "pneumonia due to coronavirus COVID-19"),
    # Endocrine / Metabolic
    ("E11.9",  "type 2 diabetes mellitus without complications"),
    ("E10.9",  "type 1 diabetes mellitus without complications"),
    ("E03.9",  "hypothyroidism unspecified underactive thyroid"),
    ("E05.90", "thyrotoxicosis hyperthyroidism without thyrotoxic crisis"),
    ("E78.5",  "hyperlipidemia hypercholesterolemia dyslipidemia"),
    ("E66.9",  "obesity unspecified BMI elevated"),
    ("E87.1",  "hyponatremia low serum sodium electrolyte disorder"),
    ("E11.65", "type 2 diabetes mellitus with hyperglycemia"),
    # Musculoskeletal
    ("M54.5",  "low back pain lumbar pain lumbago"),
    ("M17.11", "primary osteoarthritis right knee joint pain"),
    ("M06.9",  "rheumatoid arthritis unspecified inflammatory arthritis"),
    ("M81.0",  "age-related osteoporosis without current pathological fracture"),
    ("M10.9",  "gout unspecified hyperuricemia joint inflammation"),
    ("S72.001A","fracture of unspecified part of neck of right femur hip fracture"),
    ("M54.2",  "cervicalgia neck pain cervical spine"),
    # Neurological / Mental Health
    ("G40.909","epilepsy unspecified not intractable without status epilepticus seizure"),
    ("G43.909","migraine headache unspecified not intractable without status migrainosus"),
    ("G30.9",  "Alzheimer disease unspecified dementia memory loss"),
    ("F32.9",  "major depressive disorder single episode unspecified"),
    ("F41.1",  "generalized anxiety disorder GAD"),
    ("F20.9",  "schizophrenia unspecified psychosis"),
    ("G20",    "Parkinson disease tremor motor disorder"),
    ("G35",    "multiple sclerosis demyelinating disease"),
    # Genitourinary
    ("N39.0",  "urinary tract infection UTI not specified site"),
    ("N18.3",  "chronic kidney disease stage 3 moderate CKD"),
    ("N20.0",  "calculus of kidney renal stone nephrolithiasis"),
    ("N40.1",  "benign prostatic hyperplasia BPH lower urinary tract symptoms"),
    ("N92.0",  "excessive and frequent menstruation with regular cycle"),
    ("O80",    "encounter for full-term uncomplicated delivery spontaneous"),
    # Infections / Hematology
    ("A41.9",  "sepsis unspecified organism bacteremia"),
    ("B20",    "human immunodeficiency virus HIV disease AIDS"),
    ("D50.9",  "iron deficiency anemia unspecified"),
    ("D64.9",  "anemia unspecified"),
    ("C34.10", "malignant neoplasm of upper lobe lung bronchus"),
    ("C18.9",  "malignant neoplasm of colon unspecified colorectal cancer"),
    ("C50.912","malignant neoplasm of unspecified site of left female breast cancer"),
    # Skin / Eye / ENT
    ("L03.90", "cellulitis unspecified skin infection"),
    ("H25.9",  "age-related cataract unspecified lens opacity"),
    ("H35.30", "unspecified macular degeneration AMD"),
    ("H66.90", "otitis media unspecified ear infection"),
    ("J32.9",  "chronic sinusitis unspecified sinus infection"),
    # Injuries / Trauma
    ("S09.90XA","unspecified injury of head initial encounter head trauma"),
    ("T14.90", "injury unspecified"),
    ("S52.501A","unspecified fracture of the lower end of right radius Colles fracture"),
    ("T39.1X1A","poisoning by 4-Aminophenol derivatives paracetamol acetaminophen overdose"),
    # COVID / Viral
    ("U09.9",  "post-COVID-19 condition unspecified long COVID"),
    ("B34.9",  "viral infection unspecified"),
]


# ── CPT Seed Data ─────────────────────────────────────────────────────────────
CPT_SEED: list[tuple[str, str]] = [
    # Surgery – General / Abdominal
    ("44950", "appendectomy open procedure acute appendicitis"),
    ("44970", "laparoscopic appendectomy minimally invasive"),
    ("47600", "cholecystectomy open removal of gallbladder"),
    ("47562", "laparoscopic cholecystectomy minimally invasive gallbladder removal"),
    ("44140", "colectomy partial resection of colon"),
    ("43239", "esophagogastroduodenoscopy EGD with biopsy upper endoscopy"),
    ("45378", "colonoscopy diagnostic flexible lower GI endoscopy"),
    ("43280", "laparoscopic Nissen fundoplication anti-reflux surgery"),
    # Cardiovascular
    ("92928", "percutaneous coronary intervention PCI stent placement coronary artery"),
    ("33510", "coronary artery bypass grafting CABG single vessel"),
    ("93306", "echocardiography transthoracic cardiac ultrasound complete"),
    ("93000", "electrocardiogram ECG routine 12-lead with interpretation"),
    ("92960", "cardioversion external electrical defibrillation"),
    ("33274", "transcatheter pacing system insertion leadless pacemaker"),
    # Orthopedic
    ("27447", "total knee replacement arthroplasty primary"),
    ("27130", "total hip replacement arthroplasty primary"),
    ("29881", "knee arthroscopy with meniscectomy"),
    ("29827", "arthroscopy shoulder rotator cuff repair"),
    ("23472", "total shoulder arthroplasty replacement"),
    ("22612", "lumbar spinal fusion posterior approach"),
    # Neurosurgery / Neurology
    ("61510", "craniotomy for excision of brain tumor intracranial"),
    ("62270", "lumbar spinal puncture cerebrospinal fluid sampling"),
    ("95819", "electroencephalogram EEG routine awake and asleep"),
    # Obstetrics / Gynecology
    ("59400", "routine obstetric care antepartum postpartum vaginal delivery"),
    ("59510", "routine obstetric care cesarean section delivery"),
    ("58150", "total abdominal hysterectomy"),
    ("58661", "laparoscopic removal of adnexal structures"),
    # Urology
    ("52601", "transurethral resection of prostate TURP"),
    ("50590", "lithotripsy extracorporeal shockwave kidney stone"),
    ("52332", "cystoscopy ureteroscopy with stent placement"),
    # Pulmonology / Thoracic
    ("32663", "thoracoscopy VATS lobectomy lung resection"),
    ("94640", "pressurized inhalation treatment nebulizer asthma COPD"),
    ("31622", "bronchoscopy diagnostic airway inspection"),
    # Radiology / Imaging
    ("71046", "chest X-ray radiograph 2 views PA and lateral"),
    ("74177", "CT abdomen and pelvis with contrast"),
    ("70553", "MRI brain with and without contrast"),
    ("78816", "PET-CT whole body oncology imaging"),
    ("93454", "coronary angiography cardiac catheterization"),
    # Lab / Pathology
    ("85025", "complete blood count CBC with differential automated"),
    ("80053", "comprehensive metabolic panel CMP chemistry profile"),
    ("83036", "hemoglobin A1c glycated hemoglobin diabetes monitoring"),
    ("87635", "COVID-19 PCR molecular amplification"),
    ("88305", "surgical pathology tissue biopsy gross and microscopic examination"),
    # Emergency / Critical Care
    ("99285", "emergency department visit high complexity medical decision making"),
    ("99291", "critical care evaluation and management first hour ICU"),
    ("31500", "endotracheal intubation emergency airway management"),
    ("36556", "central venous catheter insertion non-tunneled"),
    # Anesthesia
    ("00840", "anesthesia intraperitoneal procedures upper abdomen"),
    ("00400", "anesthesia superficial procedures extremities trunk"),
    # Evaluation & Management
    ("99213", "office outpatient visit established patient moderate complexity"),
    ("99203", "office outpatient visit new patient moderate complexity"),
    ("99232", "subsequent hospital inpatient care moderate complexity"),
    ("99254", "inpatient consultation comprehensive evaluation"),
    # Preventive / Vaccine
    ("90686", "influenza vaccine quadrivalent 0.5 mL intramuscular"),
    ("90714", "tetanus diphtheria Td vaccine intramuscular injection"),
    ("99396", "preventive medicine reevaluation established patient 40-64 years"),
]


def seed_collection(collection, data: list[tuple[str, str]], label: str) -> None:
    existing = collection.count()
    if existing > 0:
        logger.info(f"[{label}] Collection already has {existing} entries — skipping seed.")
        logger.info(f"[{label}] To re-seed, delete the chroma_store directory first.")
        return

    ids = [f"{label}_{code}" for code, _ in data]
    documents = [description for _, description in data]
    metadatas = [{"code": code} for code, _ in data]

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    logger.info(f"[{label}] ✓ Seeded {len(data)} entries successfully.")


def main() -> None:
    logger.info("Starting ChromaDB seed operation...")

    from db.vector_store import get_icd10_collection, get_cpt_collection

    icd10_col = get_icd10_collection()
    seed_collection(icd10_col, ICD10_SEED, "ICD10")

    cpt_col = get_cpt_collection()
    seed_collection(cpt_col, CPT_SEED, "CPT")

    logger.info("Seed operation complete.")


if __name__ == "__main__":
    main()