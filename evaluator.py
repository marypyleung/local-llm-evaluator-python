# This file contains the core AI logic (NLI, Similarity, Relevance)

from sentence_transformers import SentenceTransformer, CrossEncoder, util
from transformers import pipeline
import json

class DimensionOutcomeEvaluator:
    """
    A comprehensive evaluation suite for LLM responses using local models.
    Measures performance across five dimensions: Relevance, Similarity, 
    Entailment (NLI), Scope Alignment (Coverage), and Hallucination (Grounding).
    """


    def __init__(
        self,
        embed_model = "sentence-transformers/all-mpnet-base-v2",
        cross_encoder_model = "cross-encoder/stsb-roberta-large", 
        nli_model = "roberta-large-mnli",
        use_cross_encoder = True, 
        device = -1,   # -1 for CPU, 0 for GPU
    ):
        
        """Initializes AI models for embedding, cross-encoding, and NLI."""
        # 1. Embedding Model (Sentence-Transformer)
        self.embedder = SentenceTransformer(embed_model)
        # 2. Cross-Encoder (for high-precision semantic similarity)
        self.use_cross_encoder = use_cross_encoder
        self.cross_encoder = CrossEncoder(cross_encoder_model) if use_cross_encoder else None

        # 3. NLI Model (Zero-shot logical inference)
        self.nli = pipeline(
            "text-classification",
            model=nli_model,
            device=device
        )

    # -------------------------
    # INTERNAL UTILITIES (The "Logical Brain")
    # -------------------------
    
    def _nli(self, premise, hypothesis):
        """
            Core Natural Language Inference (NLI) engine.
            
            This internal utility determines the logical relationship between two 
            text segments. It serves as the foundation for:
            - Step 3: Entailment (Fact-checking)
            - Step 4: Scope Coverage (Undergeneration)
            - Step 5: Hallunication (Grounding)
            
             Logic Flow inherited from label field of roberta-large-mnli model:
            - ENTAILMENT: The premise supports the hypothesis.
            - CONTRADICTION: The premise denies the hypothesis.
            - NEUTRAL: No logical relationship exists.
        """
        # Ensure inputs are strings to avoid model errors
        premise = str(premise or "")
        hypothesis = str(hypothesis or "")

        """
        The pipeline automatically handles dual-sentence formatting (e.g., </s></s>)
        using the 'text_pair' argument.
        """
        out_raw = self.nli(premise, text_pair=hypothesis)

        # Robust Parsing: HuggingFace pipelines return nested lists [[...]] when 
        # top_k=None is set. We unwrap this to access the dictionary.
        if isinstance(out_raw, list) and len(out_raw) > 0 and isinstance(out_raw[0], list):
            data = out_raw[0]
        else:
            data = out_raw
  

        # Now we can safely iterate over dictionaries
        try:
            # Map labels to scores and identify the winning label
            scores = {res['label'].upper(): res['score'] for res in data}
            label = max(scores, key=scores.get) 
            conf = scores.get(label, 0.0)
        except (TypeError, KeyError, ValueError):
            # Fallback for empty/malformed model outputs
            return {"label": "UNKNOWN", "confidence": 0.0, "scores": {}}
        
        return {
            "label": label,
            "confidence": round(conf, 3),
            "scores": {k: round(v, 3) for k, v in scores.items()}
        }
        

    # -------------------------
    # 1) Topic Relevance (Question vs. Actual Response)
    # -------------------------
    def topic_relevance(self, question, actual):
        """
        Measures how well the LLM response stayed on topic.
        Uses Cosine Similarity to compare the user's question with the AI's response.

        """
        q = str(question or "")
        a = str(actual or "")

        q_emb = self.embedder.encode(q, normalize_embeddings=True)
        a_emb = self.embedder.encode(a, normalize_embeddings=True)
        sim = float(util.cos_sim(q_emb, a_emb).item())

        if sim >= 0.70:
            result = "PASS"
        elif sim >= 0.50:
            result = "BORDERLINE"
        else:
            result = "FAIL"

        return {"relevance_result": result, "relevance_score": round(sim, 3)}

    # -------------------------
    # 2) Semantic Similarity (Expected vs. Actual Response)
    # -------------------------
    def semantic_similarity(self, expected, actual):
        """
        Compare the AI's response against a 'Ground Truth' answer using high-accuracy Cross-Encoder.
        """
        if not self.use_cross_encoder:
            return {"level": "SKIPPED", "similarity": None}
        
        exp = str(expected or "")
        act = str(actual or "")
        
        # Cross-Encoders usually output a raw score (0-5 or 0-1 depending on model)
        raw = float(self.cross_encoder.predict([(exp, act)])[0])

        # Cross-Encoders usually output a raw score (0-5 or 0-1 depending on model)
        sim = raw / 5.0 if raw > 1.0 else raw
        sim = max(0.0, min(1.0, sim))

        if sim >= 0.70:
            result = "PASS"

        elif sim >= 0.50:
            result = "BORDERLINE"
        else:
            result = "FAIL"


        return {"similarity_result": result, "similarity_score": round(sim, 3)}


    # -------------------------
    # 3) Entailment Outcome (Fact-Checking)
    # -------------------------
    def entailment_outcome(self, actual, claims):
        """
        Verifies Actual Response against a specific list of factual claims
        
        Simplified Fact-Checker:
        - FAIL: If ANY claim is flat-out contradicted.
        - PASS: If ALL claims are entailed.
        - BORDERLINE: If some claims are neutral/missing (Partial knowledge).
        """

        # Handle the empty string/null cases from your CSV
        if not claims or (isinstance(claims, str) and not claims.strip()):
            return {
                "entailment_result": "SKIPPED",
                "count_claims_met": "0 of 0"
            }
        
        # Strict JSON Parsing
        if isinstance(claims, str):
            try:
                # json.loads is stricter and safer than ast.literal_eval
                claims = json.loads(claims.replace("'", '"')) 
            except (json.JSONDecodeError, ValueError):
                # If it's not valid JSON, we skip it to ensure data integrity
                return {
                    "entailment_result": "SKIPPED",
                    "count_claims_met": "INVALID JSON FORMAT"
                }
            
        # Ensure we have a list of claims
        if not isinstance(claims, list):
            claims = [claims]

        total_count, entailed_count, contra_count = 0, 0, 0

        # Evaluation Loop
        for claim_text in claims:
            claim_text = str(claim_text).strip()
            if not claim_text:
                continue

            total_count += 1
            r = self._nli(actual, claim_text)
            
            if r["label"] == "ENTAILMENT":
                entailed_count += 1
            elif r["label"] == "CONTRADICTION":
                contra_count += 1

        # Verdict Logic
        if total_count == 0:
            result, count = "SKIPPED", "0 of 0"
        elif contra_count > 0:
            result, count = "FAIL", f"{entailed_count} of {total_count}"
        elif entailed_count == total_count:
            result, count = "PASS", f"{entailed_count} of {total_count}"
        else:
            result, count = "BORDERLINE", f"{entailed_count} of {total_count}"

        return {
            "entailment_result": result,
            "count_claims_met": count
        }
    
    # -------------------------
    # 4) Scope Coverage Indicator (Under-generation)
    # -------------------------
    def coverage_indicator(self, expected, actual, conf_pass=0.70):
        """
        Logic: Actual -> Expected. 
        Checks if the 'Actual' response contains the information from the 'Expected' answer.
        FAIL: The AI missed something important from the Golden Answer (Under-generation).
        """
        check = self._nli(str(actual or ""), str(expected or ""))
        if check["label"] == "ENTAILMENT" and check["confidence"] >= conf_pass:
            result = "PASS"
        elif check["label"] == "CONTRADICTION":
            result  = "FAIL"
        else:
            result  = "BORDERLINE"

        return {"coverage_result": result}

    # -------------------------
    # 5) Grounding Indicator (Hallucination)
    # -------------------------
    def grounding_indicator(self, expected, actual, conf_pass=0.70):
        """
        Logic: Expected -> Actual.
        Checks if the 'Actual' response is strictly supported by the 'Expected' answer.
        FAIL: The AI made something up that wasn't in the Golden Answer (Hallucination).
        """
        check = self._nli(str(expected or ""), str(actual or "")) 

        if check["label"] == "ENTAILMENT" and check["confidence"] >= conf_pass:
            result = "PASS"
        elif check["label"] == "CONTRADICTION":
            result = "FAIL"
        else:
            result = "BORDERLINE"

        return {"hallucination_result": result}