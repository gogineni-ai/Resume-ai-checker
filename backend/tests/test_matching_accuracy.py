import pytest
from app.services.analyzer import compare_resume_to_job, text_similarity


def test_unknown_job_skills_do_not_award_free_points():
    result = compare_resume_to_job('Python developer', 'Friendly team with excellent benefits')
    assert result['ats_score'] is None
    assert result['skill_match_score'] is None
    assert result['match_assessed'] is False


def test_stop_words_and_punctuation_do_not_crash():
    assert text_similarity('the and or', 'a an the') == 0
    assert text_similarity('!!!', '...') == 0


def test_coverage_uses_job_skills_and_does_not_reward_repetition():
    result = compare_resume_to_job('Python Python Python JavaScript', 'Python SQL PostgreSQL')
    assert result['matched_skills'] == ['python']
    assert result['missing_skills'] == ['postgresql', 'sql']
    assert result['skill_match_score'] == pytest.approx(100 / 3)
    assert result['ats_score'] < 60
