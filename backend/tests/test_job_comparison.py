from app.services.analyzer import compare_resume_to_job

def test_comparison_explains_matches_and_missing_skills():
    result = compare_resume_to_job('Built Python services.\nManaged SQL databases.', 'Python and Docker required.')
    rows = {r['skill']: r for r in result['requirements']}
    assert rows['python']['resume_excerpt'] == 'Built Python services.'
    assert rows['docker']['status'] == 'not found'
    assert rows['docker']['resume_excerpt'] is None
    assert result['skill_match_score'] == 50
    assert result['job_description'] == 'Python and Docker required.'

def test_unknown_skills_do_not_produce_false_score():
    result = compare_resume_to_job('Python', 'Friendly and reliable')
    assert result['ats_score'] is None
    assert result['requirements'] == []

def test_repeating_keywords_does_not_increase_skill_coverage():
    once = compare_resume_to_job('Python', 'Python Docker')
    repeated = compare_resume_to_job('Python ' * 100, 'Python Docker')
    assert once['skill_match_score'] == repeated['skill_match_score'] == 50
