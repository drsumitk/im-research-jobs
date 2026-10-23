"""robots.txt files copied from the live sites on 2026-10-23."""
from tracker.robots import Robots

JHU = """User-agent: *
Disallow: /
Allow: /$
Allow: /careers
Allow: /api/apply
Allow: /api/pcsx
Allow: /candidate/login
"""
WORKDAY = """Sitemap: https://wustl.wd1.myworkdayjobs.com/External/siteMap.xml

User-agent: *
Allow: /External/
Disallow: /Preboarding/
Disallow: /refreshFacet/
"""
RMK = """User-agent: *
Disallow: /applybutton/
Disallow: /services/
Disallow: /preapply/
"""
UMICH = """User-agent: *
Allow: /core/*.css$
Disallow: /core/
Disallow: /search/
"""
JIBE = """User-agent: *
Allow: /
crawl-delay: 5
"""


def test_jhu_longest_match():
    r = Robots(JHU)
    assert r.allowed("/api/pcsx/search?domain=jhu.edu&query=x")
    assert r.allowed("/careers/job/1")
    assert not r.allowed("/admin")
    assert r.allowed("/")


def test_workday_cxs_allowed():
    r = Robots(WORKDAY)
    assert r.allowed("/wday/cxs/wustl/External/jobs")
    assert not r.allowed("/refreshFacet/x")


def test_rmk_search_allowed_rss_not():
    r = Robots(RMK)
    assert r.allowed("/search/?q=postdoctoral")
    assert r.allowed("/job/Durham-Postdoctoral-Associate-NC-27710/1433460400/")
    assert not r.allowed("/services/rss/job/?keywords=x")


def test_umich_search_jobs_allowed():
    r = Robots(UMICH)
    assert r.allowed("/search-jobs?keyword=research")
    assert not r.allowed("/search/feed/advanced")
    assert r.allowed("/core/x.css") and not r.allowed("/core/x.js")


def test_crawl_delay():
    assert Robots(JIBE).crawl_delay == 5.0
    assert Robots("").allowed("/anything")


def test_bom_is_ignored():
    r = Robots("﻿User-agent: *\nDisallow: /private/\n")
    assert not r.allowed("/private/x") and r.allowed("/public")
