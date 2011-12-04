from billy.scrape.bills import BillScraper, Bill

import re
import datetime
import lxml.html

bill_id_re = re.compile('(H|S)(B|R|JR)\d+')
btn_re = re.compile('BTN(\d+)')

class ALBillScraper(BillScraper):

    state = 'al'

    def refresh_session(self):
        url = ('http://alisondb.legislature.state.al.us/acas/ACASLoginFire.asp'
               '?SESSION=%s') % self.site_id
        html = self.urlopen(url)

    def scrape(self, chamber, session):
        self.site_id = self.metadata['session_details'][session]['internal_id']

        chamber_piece = {'upper': 'Senate',
                         'lower': 'House+of+Representatives'}[chamber]
        # resolutions
        res_url = ('http://alisondb.legislature.state.al.us/acas/SESSResosBySe'
                   'lectedMatterTransResults.asp?WhichResos=%s&TransCodes='
                   '{All}&LegDay={All}') % chamber_piece
        self.scrape_for_bill_type(chamber, session, res_url)

        bill_url = ('http://alisondb.legislature.state.al.us/acas/SESSBillsByS'
                    'electedMatterTransResults.asp?TransCodes={All}'
                    '&LegDay={All}&WhichBills=%s') % chamber_piece
        self.scrape_for_bill_type(chamber, session, bill_url)


    def scrape_for_bill_type(self, chamber, session, url):

        self.refresh_session()

        with self.urlopen(url) as html:
            doc = lxml.html.fromstring(html)

            # bills are all their own table with cellspacing=4 (skip first)
            bill_tables = doc.xpath('//table[@cellspacing="4"]')
            for bt in bill_tables[1:]:

                # each table has 3 rows: detail row, description, blank
                details, desc, _ = bt.xpath('tr')

                # first <tr> has img, button, sponsor, topic, current house
                #   current status, committee, committee2, last action
                _, button, sponsor, subject, _, _, com1, com2, _ = details.xpath('td')

                # contains script tag that has a document.write that writes the
                # bill_id, we have to pull that out (gross, but only way)
                script_text = button.text_content()
                # skip SBIR/HBIR
                if 'SBIR' in script_text or 'HBIR' in script_text:
                    continue
                bill_id = bill_id_re.search(script_text).group()
                oid = btn_re.search(script_text).groups()[0]

                sponsor = sponsor.text_content()
                subject = subject.text_content()
                com1 = com1.text_content()
                com2 = com2.text_content()
                desc = desc.text_content()

                if 'B' in bill_id:
                    bill_type = 'bill'
                elif 'JR' in bill_id:
                    bill_type = 'joint resolution'
                elif 'R' in bill_id:
                    bill_type = 'resolution'

                # title is missing on a few bills
                title = desc.strip() or '(missing title)'

                # create bill
                bill = Bill(session, chamber, bill_id, title,
                            subjects=[subject])
                bill.add_sponsor('primary', sponsor)

                self.get_sponsors(bill, oid)
                self.get_actions(bill, oid)

                # craft bill URL
                session_fragment = '2010rs'
                type_fragment = 'bills'
                bill_id_fragment = bill_id.lower()
                bill_text_url = 'http://alisondb.legislature.state.al.us/acas/searchableinstruments/%s/%s/%s.htm' % (
                    session_fragment, type_fragment, bill_id_fragment)
                bill.add_version('bill text', bill_text_url)

                self.save_bill(bill)


    def get_actions(self, bill, oid):
        url = 'http://alisondb.legislature.state.al.us/acas/ACTIONHistoryResultsMac.asp?OID=%s&LABEL=%s' % (oid, bill['bill_id'])

        bill.add_source(url)

        with self.urlopen(url) as html:
            doc = lxml.html.fromstring(html)

            for row in doc.xpath('//tr[@valign="top"]'):
                tds = row.xpath('td')
                # date, amend/subst, matter, committee, nay, yea, abs, vote

                # TODO: action parsing could be greatly improved
                #   - it is unclear what it means when date is missing
                #   - nothing done with amend/subst
                #   - votes not handled yet
                #   - actor isn't provided.. unclear what can be done

                # only change date if it exists (actions w/o date get old date)
                if tds[0].text_content():
                    date = datetime.datetime.strptime(tds[0].text_content(),
                                                      '%m/%d/%Y')
                action = tds[2].text_content()
                if action:
                    bill.add_action(bill['chamber'], action, date)

    def get_sponsors(self, bill, oid):
        url = "http://alisondb.legislature.state.al.us/acas/ACTIONSponsorsResultsMac.asp?OID=%s&LABEL=%s" % (oid, bill['bill_id'])

        bill.add_source(url)

        with self.urlopen(url) as html:
            doc = lxml.html.fromstring(html)
            # cosponsors in really weird table layout (likely to break)
            for cs in doc.xpath('//table[2]/tr/td[2]/table/tr/td/text()'):
                bill.add_sponsor('cosponsor', cs)


    #def getvote(moid, bill_type, bill_number, voteid, bodyoid, sessionid):
    #    url = "http://alisondb.legislature.state.al.us/acas/GetRollCallVoteResults.asp?MOID=%s&VOTE=%s&BODY=%s&INST=%s%s&SESS=%s" % (moid,voteid,bodyoid,bill_type,bill_number,sessionid)
