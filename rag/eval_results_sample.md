# Sample-DB eval results

DB: `rag/vectordb_sample/` (1687 chunks, clips 1071/1093/1103/1124).
Retriever: hybrid RRF + date/month tags + keyword-star promotion +
word-boundary short terms + stemming + stable tiebreak.
Captured 2026-09-10. Queries defined in `eval_queries.md`.

## Scoreboard

| # | Verdict | #1 hit |
|---|---|---|
| Q1 | PASS | 1071 minutes roll call |
| Q2 | PASS | 1071 transcript @624s (funding talk) |
| Q3 | PARTIAL | 1103 minutes Sweetgrass 2nd-reading chunk (topical; exact-answer chunk outranks below — see note) |
| Q3b | PASS | all top-3 are clip 1093 (date scoping works) |
| Q4 | PASS | 1071 supporting-doc staff report |
| Q5 | PASS | 1093 transcript @1765s (keyword-star save: vector side missed) |
| Q6 | PASS | 1103 transcript opening @108s (filter held) |

### Q3 note (why PARTIAL, and why it is acceptable)

Q3 names no date, and every sampled meeting has second readings with
dissent — the question is genuinely ambiguous. The exact-answer chunk
(`1071:tx:00133`: "approved on second reading as amended with …
Laybourn and Wolfe voting no") matches 4 keyword terms but sits ~1800
chars deep, so it loses first-position tiebreaks to front-loaded minutes
chunks; its minutes mirror (`1071:min:00375`) has the vote names split
from the item header across a chunk boundary. Scoped follow-ups (Q3b)
behave correctly. Future work: minutes chunk overlap + stemmed phrase
bonus for patterns like "voting no".

## Captured outputs

### Q1 — roll call

```
collection: cheyenne_meetings @ /tmp/trwc/rag/vectordb_sample (1687 chunks, hybrid RRF)

[1] clip=1071 date=2026-03-09 src=minutes (vec_rank=50 kw_rank=1 dist=1.007)
    file=1071_2026-03-09.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1071?view_id=2&redirect=true
    [2026-03-09 March | City Council | minutes] RECORD OF PROCEEDINGS FOR THE GOVERNING BODY
OF THE CITY OF CHEYENNE
Office of City Clerk
March 9, 2026
The Governing Body of the City of Cheyenne met in regular session on this date beginning
at 6:00 p.m. in City Council Chambers  and via electronic conference meeting. Present were:
MAYOR – Patrick Collins, COUNCIL MEMBERS – Dr. Michelle Aldrich, Dr. Kathy Emmons,
Ken Esqu

[2] clip=1071 date=2026-03-09 src=transcript_clean @2103s-2251s (vec_rank=15 kw_rank=25 dist=0.895)
    file=1071_2026-03-09.clean.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1071?view_id=2&redirect=true
    [2026-03-09 March | City Council | transcript] to North College Drive. >> All right. So, I see a lot of new faces here today and that's exciting. Thank you all for being here. Um, many of you have never come and testified before city council before. So, welcome. The the way this works is we have two microphones, one on either side. Uh we'd love for you to come up and introduce yourself for the record and then we'll g

[3] clip=1071 date=2026-03-09 src=minutes (vec_rank=- kw_rank=2 dist=n/a)
    file=1071_2026-03-09.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1071?view_id=2&redirect=true
    [2026-03-09 March | City Council | minutes] permits) filed with the City Clerk’s Office.  Mr. Esquibel moved to approve, seconded by Mr.
White. Motion carried. Voting “yes” – all members of the governing body. Public comment was
made by: B ryan ‘Alf’ Grzegorczyk, Alf’s Pub and Cameron Brown, Cheba Hut. Comment was
made by the following member of the governing body: Dr. Aldrich.
No comments were made on the Voucher Re
```

### Q2 — PRCA / Project Blue Moon

```
collection: cheyenne_meetings @ /tmp/trwc/rag/vectordb_sample (1687 chunks, hybrid RRF)

[1] clip=1071 date=2026-03-09 src=transcript_clean @624s-772s (vec_rank=- kw_rank=1 dist=n/a)
    file=1071_2026-03-09.clean.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1071?view_id=2&redirect=true
    [2026-03-09 March | City Council | transcript] project. >> Laramie County and the city of Cheyenne uh will receive about $800,000 of sales tax once the museum and hall of fame are up and going. That's on an >> I don't have the state tax yet but working on it. >> And Betsy, that's on an annual basis, right? >> Yes. Yes, sir. Sorry, >> Mr. White. >> My apologies. >> U Mr. Mayor through you. Betsy, Katherine. Um and Kat

[2] clip=1071 date=2026-03-09 src=agenda (vec_rank=2 kw_rank=5 dist=0.847)
    file=agenda.html item=22 page=0
    url=https://cheyenne.granicus.com/player/clip/1071?view_id=2&redirect=true
    [2026-03-09 March | City Council | agenda] Agenda item 22: [CA] RESOLUTION – In support of the Professional Rodeo Cowboy Association (PRCA) and Professional Rodeo Hall of Fame and Museum of the American Cowboy. (FINANCE COMMITTEE)

[3] clip=1071 date=2026-03-09 src=transcript_clean @334s-477s (vec_rank=1 kw_rank=2 dist=0.746)
    file=1071_2026-03-09.clean.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1071?view_id=2&redirect=true
    [2026-03-09 March | City Council | transcript] evening. Katherine and Betsy, welcome ladies. You got it. Just pull it down so you can talk right into it. >> Yes, I'm a little shorter. Good evening, Mr. Mayor. >> Good evening. >> Good evening, city council. >> My name is Katherine Wilkinson and I am a lobbyist has been hired for once in a blue moon opportunity. Um, we'd like to speak to you on behalf of Project Blue M
```

### Q3 — second-reading no votes (ambiguous)

```
collection: cheyenne_meetings @ /tmp/trwc/rag/vectordb_sample (1687 chunks, hybrid RRF)

[1] clip=1103 date=2026-06-23 src=minutes (vec_rank=2 kw_rank=1 dist=0.852)
    file=1103_2026-06-23.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1103?view_id=2&redirect=true
    [2026-06-23 June | City Council | minutes] ORDINANCE – 2nd READING – Annexing to the City of Cheyenne, Wyoming, land east
of South Greeley Highway and south of the Sweetgrass Subdivision. Dr. Aldrich moved to approve
on second reading, seconded by Dr. Emmons. Mr. Wolfe moved to refer the ordinance to the Public
Services Committee, and the committee be instructed to report at the November 9, 2026 council
meeting, seco

[2] clip=1103 date=2026-06-23 src=minutes (vec_rank=1 kw_rank=5 dist=0.822)
    file=1103_2026-06-23.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1103?view_id=2&redirect=true
    [2026-06-23 June | City Council | minutes] Motion carried. Voting “yes” – all members of the governing body present. Public comment was
made by: Charles Miller.  During Mr. Miller’s comments, Mr. Wolfe raised a point of order that
comments were off subject.  Comments were made by the following members of the governing
body: Dr. Aldrich and Mr. Wolfe. During comments made by Mr. Wolfe, Dr. Aldrich raised a
point of or

[3] clip=1093 date=2026-04-27 src=minutes (vec_rank=23 kw_rank=2 dist=0.986)
    file=1093_2026-04-27.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1093?view_id=2&redirect=true
    [2026-04-27 April | City Council | minutes] reading, seconded by Mr. Segrave . Dr. Emmons moved to amend by substitute dated April 15,
2026, seconded by Mr. Segrave. Motion to amend by substitute  carried. Voting “yes” – all
members of the governing body. Mr. Segrave moved to refer the ordinance to the Public Services
Committee, and the c ommittee to be instructed to report at the June 8, 2026 c ouncil meeting,
secon

[4] clip=1093 date=2026-04-27 src=minutes (vec_rank=5 kw_rank=8 dist=0.883)
    file=1093_2026-04-27.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1093?view_id=2&redirect=true
    [2026-04-27 April | City Council | minutes] following member of the governing body: Dr. Rinne.
ORDINANCE –2nd READING – Amending the Official Zoning Map of the City of
Cheyenne, changing the zoning classification for land located west of Roundtop Road and adjacent
to Happy Jack Road from AG – Agricultural to BP – Business Park. Dr. Emmons advised there
was no recommendation  from Public Services Committee . Dr. Emmon

[5] clip=1071 date=2026-03-09 src=minutes (vec_rank=4 kw_rank=11 dist=0.871)
    file=1071_2026-03-09.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1071?view_id=2&redirect=true
    [2026-03-09 March | City Council | minutes] Reporting for Public Services Committee,  Dr. Emmons  moved to approve on third and final
reading, seconded by Dr. Aldrich. Motion failed. Voting “no” – all members of the governing body
with the exception of Dr. Aldrich, Mr. Laybourn and Mr. White  voting “yes”. Public comments
were made by: Kathy Scigliano, Steven Love and Chelsea McCort. Comments were made by the
followi
```

### Q3b — …at the April 27 meeting (date-scoped)

```
collection: cheyenne_meetings @ /tmp/trwc/rag/vectordb_sample (1687 chunks, hybrid RRF)

[1] clip=1093 date=2026-04-27 src=minutes (vec_rank=30 kw_rank=1 dist=0.959)
    file=1093_2026-04-27.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1093?view_id=2&redirect=true
    [2026-04-27 April | City Council | minutes] normal sequence on the agenda). Upon request by Mr. Laybourn, and pursuant to support received
by Mr. Moody and Mr. White, item #15 was removed from the Consent Agenda. Upon request by
Mr. Laybourn, and pursuant to support received by Mr. Moody and Mr. Wolfe , item #29(a) was
removed from the Consent Agenda. Upon request by Mr. Laybourn, and pursuant to support
received by

[2] clip=1093 date=2026-04-27 src=minutes (vec_rank=2 kw_rank=4 dist=0.769)
    file=1093_2026-04-27.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1093?view_id=2&redirect=true
    [2026-04-27 April | City Council | minutes] following member of the governing body: Dr. Rinne.
ORDINANCE –2nd READING – Amending the Official Zoning Map of the City of
Cheyenne, changing the zoning classification for land located west of Roundtop Road and adjacent
to Happy Jack Road from AG – Agricultural to BP – Business Park. Dr. Emmons advised there
was no recommendation  from Public Services Committee . Dr. Emmon

[3] clip=1093 date=2026-04-27 src=minutes (vec_rank=7 kw_rank=2 dist=0.846)
    file=1093_2026-04-27.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1093?view_id=2&redirect=true
    [2026-04-27 April | City Council | minutes] reading, seconded by Mr. Segrave . Dr. Emmons moved to amend by substitute dated April 15,
2026, seconded by Mr. Segrave. Motion to amend by substitute  carried. Voting “yes” – all
members of the governing body. Mr. Segrave moved to refer the ordinance to the Public Services
Committee, and the c ommittee to be instructed to report at the June 8, 2026 c ouncil meeting,
secon
```

### Q4 — Harmony Valley

```
collection: cheyenne_meetings @ /tmp/trwc/rag/vectordb_sample (1687 chunks, hybrid RRF)

[1] clip=1071 date=2026-03-09 src=supporting_doc (vec_rank=18 kw_rank=1 dist=0.889)
    file=clip1071_2026-03-09/item_10_meta146451_13-ORDINANCE-1st-READING-Amending-the-Official-Zoning-Map-of-the-City.pdf item=item_10_meta146451_13-ORDINANCE-1st-READING-Amending-the-Official-Zoning-Map-of- page=2
    url=https://cheyenne.granicus.com/player/clip/1071?view_id=2&redirect=true
    [2026-03-09 March | City Council | doc] amendment that is the subject of this ordinance meets the criteria specified in Section 2.2.1.d of
the UDC.
Section 4.  That, in accordance with Section 2.2.1, Zoning Map Amendment, Section 5.1.2,
Zoning Districts Established, and Section 5.1.3 , Official Zoning Map , of the UDC, the
aforementioned zoning map amendment application is hereby approved and the zoning
classificatio

[2] clip=1071 date=2026-03-09 src=supporting_doc (vec_rank=1 kw_rank=6 dist=0.702)
    file=clip1071_2026-03-09/item_11_meta146453_14-ORDINANCE-1st-READING-Amending-the-Official-Zoning-Map-of-the-City.pdf item=item_11_meta146453_14-ORDINANCE-1st-READING-Amending-the-Official-Zoning-Map-of- page=5
    url=https://cheyenne.granicus.com/player/clip/1071?view_id=2&redirect=true
    [2026-03-09 March | City Council | doc] PUDC-26-27   March 2, 2026
2 | P a g e
RECOMMENDED MOTION:
Move to approve the rezoning of Lot 2, Block 10, Harmony Valley , 1st Filing to NR-3 Neighborhood
Residential – High Density as shown in the attached zone change map , noting that the project meets the
review criteria for approval .
APPLICABLE CITY CODE SECTION(S) AND PLANS:
• UDC 2.2.1 Zoning Map Amendment
• UDC Articl

[3] clip=1071 date=2026-03-09 src=supporting_doc (vec_rank=42 kw_rank=2 dist=0.951)
    file=clip1071_2026-03-09/item_10_meta146451_13-ORDINANCE-1st-READING-Amending-the-Official-Zoning-Map-of-the-City.pdf item=item_10_meta146451_13-ORDINANCE-1st-READING-Amending-the-Official-Zoning-Map-of- page=2
    url=https://cheyenne.granicus.com/player/clip/1071?view_id=2&redirect=true
    [2026-03-09 March | City Council | doc] ORDINANCE NO. ________
ENTITLED: "AN ORDINANCE AMENDING THE OFFICIAL ZONING MAP OF THE
CITY OF CHEYENNE , CHANGING THE ZONING CLASSIFICATION
FOR LAND LOCATED NORTH OF WEST COLLEGE DRIVE AND EAST
OF SOUTH PARSLEY BOULEVARD  FROM PUD HARMONY VALLEY
PLANNED UNIT DEVELOPMENT  TO NR-3 NEIGHBORHOOD
RESIDENTIAL – HIGH DENSITY.”
BE IT ORDAINED BY THE GOVERNING BODY OF THE CITY OF CHEYE
```

### Q5 — Via West postponement

```
collection: cheyenne_meetings @ /tmp/trwc/rag/vectordb_sample (1687 chunks, hybrid RRF)

[1] clip=1093 date=2026-04-27 src=transcript_clean @1765s-1921s (vec_rank=- kw_rank=1 dist=n/a)
    file=1093_2026-04-27.clean.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1093?view_id=2&redirect=true
    [2026-04-27 April | City Council | transcript] use or not. But it doesn't give people the same access as what a public park would have um had that entire 60 plus acres been converted into a park. Um, I am going to go ahead and vote for this this evening because I believe that um our community wreck and events team is um stretched thin with um maintenance and upkeep of parks as well as there's a big need for more floo

[2] clip=1093 date=2026-04-27 src=transcript_clean @11513s-11658s (vec_rank=12 kw_rank=5 dist=1.351)
    file=1093_2026-04-27.clean.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1093?view_id=2&redirect=true
    [2026-04-27 April | City Council | transcript] classic. Uh, you cannot point of order a physical reality. Whether we are on an amendment, an annexation, or a zoning change, the foundational legal requirement remains the same. >> Mr. Miller, again, I've got a motion in a second to call you out of order. And I agree, sir. You're out of order. You're not following our procedures. And I'm sorry, I can't call you out of o

[3] clip=1093 date=2026-04-27 src=minutes (vec_rank=- kw_rank=2 dist=n/a)
    file=1093_2026-04-27.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1093?view_id=2&redirect=true
    [2026-04-27 April | City Council | minutes] reading, seconded by Mr. Segrave . Dr. Emmons moved to amend by substitute dated April 15,
2026, seconded by Mr. Segrave. Motion to amend by substitute  carried. Voting “yes” – all
members of the governing body. Mr. Segrave moved to refer the ordinance to the Public Services
Committee, and the c ommittee to be instructed to report at the June 8, 2026 c ouncil meeting,
secon
```

### Q6 — clip-filtered opening

```
collection: cheyenne_meetings @ /tmp/trwc/rag/vectordb_sample (1687 chunks, hybrid RRF)

[1] clip=1103 date=2026-06-23 src=transcript_clean @108s-251s (vec_rank=18 kw_rank=1 dist=1.258)
    file=1103_2026-06-23.clean.txt item= page=0
    url=https://cheyenne.granicus.com/player/clip/1103?view_id=2&redirect=true
    [2026-06-23 June | City Council | transcript] Recording in progress. Good evening and welcome to the June 22nd city council meeting. I will uh I Mayor Collins is not available tonight so we'll have to suffer through me. I apologize in advance. Uh with that could um could we call roll please? >> Mr. White >> present. >> Mr. Wolfe >> here. >> Dr. Aldrich present. Mayor Collins. >> Dr. Dr. Emmons >> present. >> Mr. Esqu

[2] clip=1103 date=2026-06-23 src=supporting_doc (vec_rank=5 kw_rank=6 dist=1.179)
    file=clip1103_2026-06-23/item_27_meta148969_30-CA-RESOLUTION-Authorizing-the-City-of-Cheyenne-to-accept-and-implem.pdf item=item_27_meta148969_30-CA-RESOLUTION-Authorizing-the-City-of-Cheyenne-to-accept-a page=3
    url=https://cheyenne.granicus.com/player/clip/1103?view_id=2&redirect=true
    [2026-06-23 June | City Council | doc] the City to expend funds in excess of amounts lawfully appropriated or otherwise available for the
purposes stated herein.
PRESENTED, READ AND ADOPTED THIS _______ DAY OF __________________,
2026.
__________________________________________
Patrick Collins, Mayor
(SEAL)
ATTEST:
____________________________________
Kylie Soden, City Clerk
```
