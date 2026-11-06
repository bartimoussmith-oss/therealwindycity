"""Durable onboarding policy for generated Wyoming instances; no network I/O."""
import copy
import json
import shlex
from datetime import date
from urllib.parse import urlsplit

CONTACT = 'https://github.com/bartimoussmith-oss/therealwindycity/issues'

def https_url(value):
    if not isinstance(value, str):
        raise ValueError('URL must be a string')
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Expected credential-free HTTPS URL')
    return value

def url_set(value):
    if not isinstance(value, list):
        raise ValueError('URL policy must be a list')
    return {https_url(url) for url in value}

def load_policy(root):
    path = root / 'wyoming/onboarding.json'
    if not path.exists():
        return {'jurisdictions': {}}
    policy = json.loads(path.read_text())
    if not isinstance(policy, dict) or not isinstance(policy.get('jurisdictions', {}), dict):
        raise ValueError('Invalid onboarding document')
    return policy

def install(namespace):
    original_registry = namespace['load_registry']
    original_sources = namespace['sources_for']
    original_facts = namespace['facts_for']
    original_env = namespace['env_sh_for']
    original_readme = namespace['readme_for']
    original_verification = namespace['load_verification']
    root = namespace['ROOT']

    def local(entry):
        item = load_policy(root).get('jurisdictions', {}).get(entry['slug'], {})
        if not isinstance(item, dict):
            raise ValueError('Jurisdiction onboarding must be an object')
        return item

    def registry():
        value = original_registry()
        items = load_policy(root).get('jurisdictions', {})
        known = {entry['slug'] for entry in value['jurisdictions']}
        if set(items) - known:
            raise ValueError('Onboarding contains unknown jurisdiction slugs')
        for entry in value['jurisdictions']:
            item = local(entry)
            for key in ('approved_source_urls', 'source_reviews'):
                if key in item:
                    entry[key] = copy.deepcopy(item[key])
            entry['denied_source_urls'] = sorted(url_set(entry.get('denied_source_urls', [])) | url_set(item.get('denied_source_urls', [])))
            approved_urls(entry)
        return value

    def approved_urls(entry):
        item = local(entry)
        approved = url_set(item.get('approved_source_urls', entry.get('approved_source_urls', [])))
        denied = url_set(entry.get('denied_source_urls', [])) | url_set(item.get('denied_source_urls', []))
        reviews = item.get('source_reviews', entry.get('source_reviews', {}))
        if not isinstance(reviews, dict):
            raise ValueError('source_reviews must be an object')
        for url in approved - denied:
            review = reviews.get(url, {})
            if not isinstance(review, dict) or not review.get('reviewer'):
                raise ValueError('Approved URL requires reviewer evidence: ' + url)
            https_url(review.get('source_url'))
            date.fromisoformat(review.get('reviewed_on', ''))
        return approved - denied

    def verification(slug):
        value = original_verification(slug)
        if not value:
            return None
        registry = namespace['load_registry']()
        entry = next((e for e in registry['jurisdictions'] if e['slug'] == slug), None)
        if entry is None or value.get('verified_url') not in approved_urls(entry):
            return None
        return value

    def sources(entry):
        config = original_sources(entry)
        for source in config['sources']:
            if source['name'] == entry['slug'] + '_homepage':
                source['notes'] = 'Candidate URL: enable only after reviewed-source approval and a successful robots-compliant live probe.'
        approved = approved_urls(entry)
        for source in config['sources']:
            if source.get('enabled') and source['url'] not in approved:
                source['enabled'] = False
                source['notes'] += ' Disabled by reviewed-source policy.'
        identity = config['identity']
        identity['contact'] = CONTACT
        identity['user_agent'] = 'WyomingCivicTransparencyEngine/0.2 (public-records research; contact: ' + CONTACT + ')'
        return config

    def facts(entry):
        result = original_facts(entry)
        result['owner_todo'] = [text.replace('live-fetches and enables only what actually answers; honors robots.txt', 'requires reviewed approved URLs; honors robots.txt').replace('odd-numbered years', 'even-numbered years (town-election exceptions: W.S. 22-23-201/202)') for text in result.get('owner_todo', [])]
        overrides = local(entry).get('facts', {})
        if not isinstance(overrides, dict):
            raise ValueError('facts override must be an object')
        for key, value in overrides.items():
            if key not in {'site', 'timeline', 'question_of_the_week', 'owner_todo', 'notes'}:
                raise ValueError('Unknown facts key: ' + key)
            if key == 'site':
                if not isinstance(value, dict):
                    raise ValueError('site must be an object')
                result['site'].update(copy.deepcopy(value))
            else:
                result[key] = copy.deepcopy(value)
        if not isinstance(result.get('timeline'), list):
            raise ValueError('timeline must be a list')
        for event in result['timeline']:
            if not isinstance(event, dict) or not event.get('label'):
                raise ValueError('Timeline entry requires a label')
            date.fromisoformat(event.get('date', ''))
            https_url(event.get('url'))
        if 'question_of_the_week' in result:
            question = result['question_of_the_week']
            if not isinstance(question, dict):
                raise ValueError('question_of_the_week must be an object')
            https_url(question.get('url'))
        if result['site'].get('election_day'):
            date.fromisoformat(result['site']['election_day'])
            https_url(local(entry).get('election_source_url'))
        return result

    def custodian_for(entry):
        value = local(entry).get('custodian')
        if value is None:
            return None
        if not isinstance(value, dict) or not value.get('office') or not value.get('address'):
            raise ValueError('Custodian requires office and address')
        https_url(value.get('source_url'))
        date.fromisoformat(value.get('reviewed_on', ''))
        if not value.get('reviewer'):
            raise ValueError('Custodian requires reviewer')
        return value

    def env(entry):
        value = custodian_for(entry)
        if value is None:
            return original_env(entry)
        return ('# Reviewed public-office contact; source: ' + value['source_url'] + '\n' +
                'export ENGINE_CUSTODIAN_OFFICE=' + shlex.quote(value['office']) + '\n' +
                'export ENGINE_CUSTODIAN_ADDRESS=' + shlex.quote(value['address']) + '\n' +
                'export ENGINE_WARD_OR_AREA=' + shlex.quote(entry['name']) + '\n')

    def readme(entry):
        text = original_readme(entry)
        text = text.replace('## Status: GENERATED, UNVERIFIED', '## Status: inspect source approvals and verification.json')
        text = text.replace('No source in this instance has been fetched. Every source is `enabled: false`.', 'Sources require reviewed URL approval and a successful live probe before enabling.')
        text = text.replace('probe candidate official URLs; writes `verification.json` here.', 'report candidate reachability without writing instance files.')
        text = text.replace('enable what genuinely answered (robots.txt honored).', 'apply reviewed-source policy and current reachability (robots.txt honored).')
        text = text.replace('Add the local record to `config/facts.json`', 'Store the local record in `wyoming/onboarding.json` under this slug and its facts key')
        text = text.replace('Confirm the custodian office/address in `env.sh` (currently UNVERIFIED placeholders).', 'Store a reviewed custodian in `wyoming/onboarding.json`; unreviewed instances retain placeholders.')
        text = text.replace('add manual source URLs to', 'record reviewed source URLs in')
        text = text.replace('`config/sources.json` only after', '`wyoming/onboarding.json` only after')
        text = text.replace('Empty timeline, no question_of_the_week, zero enabled sources: this instance asserts nothing yet.', 'Default instances have no local facts. Reviewed facts and source approvals are retained in the onboarding document.')
        return text

    namespace.update(readme_for=readme, load_registry=registry, sources_for=sources, facts_for=facts, env_sh_for=env,
                     load_verification=verification, approved_urls=approved_urls,
                     custodian_for=custodian_for)


def migrate():
    """One-time, preimage-checked migration. Run only on the repair branch."""
    import hashlib
    import importlib
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / 'tools'))
    generator_path = root / 'tools/wyoming_instantiate.py'
    tests_path = root / 'tools/test_wyoming_instantiate.py'
    generator = generator_path.read_text()
    tests = tests_path.read_text()
    marker = '# onboarding-policy-migration-v1'
    def blob(text):
        raw = text.encode()
        return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if marker not in generator and blob(generator) != '0410ff06046c27d6fdb5ae9921a976330e78588f':
        raise ValueError('Generator changed: inspect before migrating')
    if marker not in tests and blob(tests) != '392c463f10baf3464d6d9b14499c71febb17ab7a':
        raise ValueError('Instantiation tests changed: inspect before migrating')
    import wyoming_instantiate as gen
    policy_path = root / 'wyoming/onboarding.json'
    document = load_policy(root)
    document.setdefault('schema_version', 1)
    items = document.setdefault('jurisdictions', {})
    for entry in gen.load_registry()['jurisdictions']:
        directory = gen.INSTANCES_DIR / entry['slug']
        facts_path = directory / 'config/facts.json'
        if facts_path.exists():
            current = json.loads(facts_path.read_text())
            if current != gen.facts_for(entry):
                items.setdefault(entry['slug'], {})['facts'] = current
        env_path = directory / 'env.sh'
        if env_path.exists() and env_path.read_text() != gen.env_sh_for(entry):
            raise ValueError('Custom custodian file requires explicit reviewed onboarding first: ' + entry['slug'])
    if marker not in generator:
        anchor = 'if __name__ == "__main__":'
        if generator.count(anchor) != 1:
            raise ValueError('Generator entrypoint anchor is ambiguous')
        hook = marker + '\nfrom wyoming_policy import install as _install_onboarding\n_install_onboarding(globals())\n\n'
        generator = generator.replace(anchor, hook + anchor)
    if marker not in tests:
        replacements = [
            ('if any(s.get("enabled") for s in cfg["sources"]):',
             'if any(s.get("enabled") and s["url"] not in gen.approved_urls(e) for s in cfg["sources"]):'),
            ('if facts["timeline"] != []:',
             'if any(not isinstance(item, dict) or not item.get("url") for item in facts["timeline"]):'),
            ('if "question_of_the_week" in facts:',
             'if "question_of_the_week" in facts and not facts["question_of_the_week"].get("url"):'),
            ('if "UNVERIFIED" not in (gen.INSTANCES_DIR / e["slug"] / "env.sh").read_text()]',
             'if not gen.custodian_for(e) and "UNVERIFIED" not in (gen.INSTANCES_DIR / e["slug"] / "env.sh").read_text()]'),
        ]
        for old, new in replacements:
            if tests.count(old) != 1:
                raise ValueError('Instantiation test anchor is ambiguous: ' + old)
            tests = tests.replace(old, new)
        tests = marker + '\n' + tests
    compile(generator, str(generator_path), 'exec')
    compile(tests, str(tests_path), 'exec')
    policy_path.write_text(json.dumps(document, indent=2) + '\n')
    generator_path.write_text(generator)
    tests_path.write_text(tests)
    importlib.invalidate_caches()
    gen = importlib.reload(gen)
    entries = gen.load_registry()['jurisdictions']
    for entry in entries:
        gen.render_instance(entry)
    for entry in entries:
        gen.write_instance(entry)
    config_path = root / 'config/sources.json'
    if config_path.exists():
        config = json.loads(config_path.read_text())
        identity = config.get('identity', {})
        for key in ('contact', 'user_agent'):
            if 'you@example.org' in str(identity.get(key, '')):
                if key == 'contact':
                    identity[key] = CONTACT
                else:
                    identity[key] = identity[key].replace('you@example.org', CONTACT)
        config_path.write_text(json.dumps(config, indent=2) + '\n')
    drift = [item for entry in entries for item in gen.check_instance(entry)]
    if drift:
        raise ValueError('Post-migration instance drift: ' + repr(drift[:10]))
    print(json.dumps({'instances': len(entries), 'drift': len(drift), 'migration': 'prepared; commit only after tests pass'}))


def selftest():
    """Exercise the installed policy against the real generator in a temp tree."""
    import importlib.util
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / 'tools').mkdir()
        (root / 'wyoming').mkdir()
        entry = {'slug': 'fixture', 'name': 'Fixture', 'type': 'town', 'county': None, 'population_2020': 1}
        registry = {'counts': {'total_instances': 1}, 'jurisdictions': [entry]}
        (root / 'wyoming/registry.json').write_text(json.dumps(registry))
        generator = Path(__file__).resolve().with_name('wyoming_instantiate.py').read_text()
        target = root / 'tools/wyoming_instantiate.py'
        target.write_text(generator)
        spec = importlib.util.spec_from_file_location('wyoming_policy_fixture', target)
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        assert not any(source.get('enabled') for source in gen.sources_for(entry)['sources'])
        assert 'you@example.org' not in str(gen.sources_for(entry))
        assert 'odd-numbered years' not in str(gen.facts_for(entry))
        gen.write_instance(entry)
        assert gen.write_instance(entry) == []
        onboarding = root / 'wyoming/onboarding.json'
        url = 'https://example.gov'
        item = {'approved_source_urls': [url], 'source_reviews': {url: {'reviewer': 'fictional test reviewer', 'source_url': 'https://example.gov/directory', 'reviewed_on': '2026-11-06'}}}
        def save():
            onboarding.write_text(json.dumps({'jurisdictions': {'fixture': item}}))
        save()
        assert url in gen.approved_urls(entry)
        assert not any(source.get('enabled') for source in gen.sources_for(entry)['sources'])
        directory = root / 'wyoming/instances/fixture'
        (directory / 'verification.json').write_text(json.dumps({'verification': 'live-verified', 'verified_url': url, 'checked_at': '2026-11-06T00:00:00Z'}))
        assert any(source.get('enabled') for source in gen.sources_for(entry)['sources'])
        item['facts'] = {'timeline': [{'date': '2026-11-06', 'label': 'Fictional test record', 'url': url + '/record'}]}
        save()
        gen.write_instance(entry)
        assert json.loads((directory / 'config/facts.json').read_text())['timeline'][0]['label'] == 'Fictional test record'
        item['custodian'] = {'office': "Fixture Clerk's Office", 'address': 'Fictional test address', 'source_url': url + '/clerk', 'reviewer': 'test fixture', 'reviewed_on': '2026-11-06'}
        save()
        gen.write_instance(entry)
        assert 'UNVERIFIED' not in (directory / 'env.sh').read_text()
        item['denied_source_urls'] = [url]
        save()
        gen.write_instance(entry)
        assert not any(source.get('enabled') for source in gen.sources_for(entry)['sources'])
        assert gen.check_instance(entry) == []
        assert gen.load_registry()['jurisdictions'][0]['denied_source_urls'] == [url]
        print('12 real-generator policy integration assertions passed; synthetic fixture, no network')

if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['--migrate']:
        migrate()
    elif sys.argv[1:] == ['--selftest']:
        selftest()
    else:
        raise SystemExit('Usage: python3 tools/wyoming_policy.py --migrate|--selftest')
