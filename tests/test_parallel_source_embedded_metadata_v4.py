"""Authored region-merging attacks; no empirical source-quality claim."""
import unittest

from test_parallel_source_v4 import ABSTRACT, assess, line
from src.parallel_source_v4.adapters import document, item
from trace_gc.pdf_source_parallel_v4 import validate_source_spans
from trace_gc.pdf_structure_parallel_v4 import verify_assessment


SUFFIXES = (
    "Department of Physics, University of Example.",
    "This work was funded by the Example Foundation.",
    "Figure 1: The transport network used for all experiments.",
)


class EmbeddedMetadataTests(unittest.TestCase):
    def assert_held(self, result, native, suffix):
        self.assertEqual(result["status"], "uncertain", result)
        self.assertFalse(result["proposal"])
        self.assertFalse(result["complete_candidate"])
        self.assertIsNone(result["section_owner"])
        self.assertIn("embedded_nonabstract_role_requires_source_review", result["reasons"])
        self.assertIn(suffix, result["text"])
        boundary = result["closing_boundary"]
        self.assertEqual(boundary["version"], "source-embedded-nonabstract-role-hold-v1")
        self.assertEqual(boundary["source_location"], "located")
        self.assertTrue(boundary["source_spans"])
        validate_source_spans(boundary["source_spans"], native)
        self.assertFalse(result["eligible_for_jev"])
        self.assertFalse(result["verified_admission"])
        verify_assessment(result)

    def test_merged_region_affiliation_funding_and_caption_are_not_complete(self):
        for suffix in SUFFIXES:
            for separator in ("\n", " "):
                with self.subTest(suffix=suffix, separator=repr(separator)):
                    native = [line(0, "Abstract " + ABSTRACT, 100), line(1, suffix, 125),
                              line(2, "1 Introduction", 190)]
                    doc = document([item(0, native[0]["text"] + separator + suffix, "text", [[40, 100, 280, 137]]),
                                    item(1, "1 Introduction", "section_header", [native[2]["bbox"]])])
                    self.assert_held(assess(native, doc), native, suffix)

    def test_same_native_line_metadata_suffix_is_held_without_truncation(self):
        for suffix in SUFFIXES:
            with self.subTest(suffix=suffix):
                native = [line(0, "Abstract " + ABSTRACT + " " + suffix, 100),
                          line(1, "1 Introduction", 190)]
                self.assert_held(assess(native), native, suffix)

    def test_separate_metadata_regions_retain_existing_source_bound_cut(self):
        for suffix in SUFFIXES:
            with self.subTest(suffix=suffix):
                native = [line(0, "Abstract " + ABSTRACT, 100), line(1, suffix, 125),
                          line(2, "1 Introduction", 190)]
                result = assess(native)
                self.assertTrue(result["proposal"], result)
                self.assertEqual(result["text"], ABSTRACT)
                self.assertNotIn(suffix, result["text"])
                validate_source_spans(result["closing_boundary"]["source_spans"], native)

    def test_explicit_role_labels_and_noncapitalized_suffixes_are_held(self):
        for suffix in ("Affiliations: University of Example.",
                       "affiliation: Institute of Example.",
                       "funding: Example Foundation grant 123.",
                       "Corresponding author: Alice Smith.",
                       "this work was supported by the Example Foundation.",
                       "figure 1: The transport network.",
                       "1 Department of Physics, University of Example.",
                       "© 2026 Example Publisher. All rights reserved."):
            with self.subTest(suffix=suffix):
                native = [line(0, "Abstract " + ABSTRACT + " " + suffix, 100),
                          line(1, "1 Introduction", 190)]
                self.assert_held(assess(native), native, suffix)

    def test_new_explicit_role_labels_split_into_separate_regions_stay_held(self):
        for suffix in ("Affiliations: University of Example.", "Corresponding author: Alice Smith."):
            with self.subTest(suffix=suffix):
                native = [line(0, "Abstract " + ABSTRACT, 100), line(1, suffix, 125),
                          line(2, "1 Introduction", 190)]
                self.assert_held(assess(native), native, suffix)

    def test_existing_explicit_funding_label_still_excludes_metadata(self):
        native = [line(0, "Abstract " + ABSTRACT + " Funding: Example Foundation grant 123.", 100),
                  line(1, "1 Introduction", 190)]
        result = assess(native)
        self.assertTrue(result["proposal"], result)
        self.assertEqual(result["text"], ABSTRACT)
        self.assertEqual(result["closing_boundary"]["kind"], "embedded_metadata")
        self.assertEqual(result["closing_boundary"]["label"], "Funding")
        verify_assessment(result)

    def test_bounded_markers_do_not_hide_known_role_suffixes(self):
        for marker in ("*", "†", "‡", "1", "1,2", "a"):
            for label in ("Corresponding author: Alice Smith.",
                          "Affiliations: University of Example.",
                          "funding: Example Foundation grant 123.",
                          "Figure 1: The transport network."):
                for separator in (" ", "\n"):
                    suffix = marker + " " + label
                    with self.subTest(marker=marker, label=label, separator=repr(separator)):
                        native = [line(0, "Abstract " + ABSTRACT + separator + suffix, 100),
                                  line(1, "1 Introduction", 190)]
                        self.assert_held(assess(native), native, suffix)

    def test_existing_sentence_tail_grammar_cannot_hide_role_suffixes(self):
        for tail in ('." ', ".) ", ".1 ", ".' ", ".† ", ". 1 ", ". ” ", ".] "):
            for suffix in (SUFFIXES[0], "Corresponding author: Alice Smith.",
                           "funding: Example Foundation grant 123."):
                with self.subTest(tail=tail, suffix=suffix):
                    native = [line(0, "Abstract " + ABSTRACT.rstrip(".") + tail + suffix, 100),
                              line(1, "1 Introduction", 190)]
                    self.assert_held(assess(native), native, suffix)

    def test_wrapped_role_words_and_figure_references_remain_source_prose(self):
        for before, after in (("These observations", "highlight the measured response."),
                              ("The next comparison is shown below.", "Figure 1 shows a stable response."),
                              ("These", "highlights of the analysis explain the response."),
                              ("These findings show how", "a university can improve the response."),
                              ("These observations", "highlight\nthe measured response."),
                              ("Our implementation is available at", "https://example.org/artifact.")):
            with self.subTest(before=before, after=after):
                native = [line(0, "Abstract " + ABSTRACT + " " + before, 100),
                          line(1, after, 125), line(2, "Keywords: measurements", 190)]
                doc = document([item(0, native[0]["text"] + " " + after, "text", [[40, 100, 280, 137]]),
                                item(1, native[2]["text"], "text", [native[2]["bbox"]])])
                result = assess(native, doc)
                self.assertTrue(result["proposal"], result)
                self.assertIn(after, result["text"])
                self.assertEqual(result["closing_boundary"]["kind"], "metadata_or_nonabstract_region")
                verify_assessment(result)

    def test_institution_adjectives_are_not_affiliation_roles(self):
        for term in ("Laboratory-achievable", "University-based", "Laboratory-\nachievable"):
            with self.subTest(term=term):
                prose = term + " measurements reproduce the estimated response."
                native = [line(0, "Abstract " + ABSTRACT + " " + prose, 100),
                          line(1, "Keywords: measurements", 190)]
                result = assess(native)
                self.assertTrue(result["proposal"], result)
                self.assertIn(prose, result["text"])
                verify_assessment(result)

    def test_explicit_nonabstract_labels_and_separate_url_still_hold(self):
        for suffix in ("highlights: An authored summary.", "Highlights\nAn authored summary.",
                       "highlight: An authored summary.", "a University of Example.",
                       "1 university: Example Institute.",
                       "Figure 1. The transport network.", "graphical abstract: An authored summary.",
                       "https://example.org/contact"):
            with self.subTest(suffix=suffix):
                native = [line(0, "Abstract " + ABSTRACT + " " + suffix, 100),
                          line(1, "1 Introduction", 190)]
                self.assert_held(assess(native), native, suffix)

    def test_role_words_inside_running_sentence_do_not_change_abstract(self):
        prose = ("We study department affiliations, funding decisions and Figure 1 in a single analysis. "
                 "The university supports several controlled experiments. "
                 "Corresponding authors coordinate the measured networks.")
        native = [line(0, "Abstract " + ABSTRACT + " " + prose, 100), line(1, "Keywords: transport", 190)]
        result = assess(native)
        self.assertTrue(result["proposal"], result)
        self.assertEqual(result["text"], ABSTRACT + " " + prose)

    def test_ambiguous_role_prefix_never_certifies_a_truncated_prefix(self):
        # This could be ordinary abstract prose. The role cue is not permission
        # to delete it and approve only the preceding sentences.
        suffix = "University education changes the measured network response."
        native = [line(0, "Abstract " + ABSTRACT + " " + suffix, 100), line(1, "1 Introduction", 190)]
        self.assert_held(assess(native), native, suffix)

    def test_converter_invented_metadata_has_no_source_witness(self):
        native = [line(0, "Abstract " + ABSTRACT, 100), line(1, "1 Introduction", 190)]
        fake = "This work was funded by " + "invented provenance " * 25
        doc = document([item(0, native[0]["text"] + " " + fake, "text", [native[0]["bbox"]]),
                        item(1, "1 Introduction", "section_header", [native[1]["bbox"]])])
        result = assess(native, doc)
        self.assertFalse(result["proposal"], result)
        self.assertNotEqual(result["status"], "complete")
        verify_assessment(result)

    def test_structured_abstract_keeps_all_subsections_while_role_is_unresolved(self):
        text = ("Context: " + ABSTRACT + "\nMethods: We repeat all measurements.\n"
                "Results: The estimates remain stable.\nConclusions: The model predicts transport.")
        suffix = SUFFIXES[1]
        native = [line(0, "Abstract " + text + "\n" + suffix, 100), line(1, "1 Introduction", 190)]
        result = assess(native)
        self.assert_held(result, native, suffix)
        for label in ("Context:", "Methods:", "Results:", "Conclusions:"):
            self.assertIn(label, result["text"])

    def test_source_supported_non_english_paragraph_does_not_need_english_verbs(self):
        for text in (
            "Les mesures du réseau décrivent une relation stable entre la connectivité et la réponse. "
            "Les observations obtenues dans plusieurs conditions confirment la précision des estimations.",
            "Die Messungen des Netzwerks beschreiben einen stabilen Zusammenhang zwischen Verbindung und Reaktion. "
            "Die Beobachtungen unter mehreren Bedingungen bestätigen die Genauigkeit der Schätzungen.",
        ):
            with self.subTest(text=text[:12]):
                native = [line(0, text, 100), line(1, "Keywords: networks", 190)]
                result = assess(native, scholarly_abstract=text)
                self.assertTrue(result["proposal"], result)
                self.assertEqual(result["text"], text)
                verify_assessment(result)


if __name__ == "__main__":
    unittest.main()
