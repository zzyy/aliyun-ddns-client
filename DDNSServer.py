#!/usr/bin/env python
# coding=utf-8

from http.server import BaseHTTPRequestHandler, HTTPServer, HTTPStatus
from urllib.parse import urlparse, parse_qs
from ddns import DDNSUtils
from config import DDNSConfig
from yunresolver import YunResolver
from record import RemoteDomainRecord


class RequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.config = DDNSConfig()
        self.resolver = YunResolver(self.config.access_id, self.config.access_key, self.config.debug)

        try:
            query_str = urlparse(self.path).query
            query_map = parse_qs(query_str)
            domain = query_map.get("domain")[0]
            sub_domain = query_map.get("sub_domain")[0]
            request_ip = self.client_address[0]
            DDNSUtils.info("request info; ip:%s, dns: %s.%s" % (request_ip, sub_domain, domain))

            result_msg = self.update_aliyun_dns_if_need(request_ip, sub_domain, domain)

            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header("Content-Length", str(len(result_msg)))
            self.end_headers()
            self.wfile.write(result_msg.encode('utf-8'))
        except Exception as e:
            self.send_error(400, repr(e))

    def update_aliyun_dns_if_need(self, ip, sub_domain, domain, type="A"):
        dns_resolved_ip = DDNSUtils.get_dns_resolved_ip(sub_domain, domain)
        if ip == dns_resolved_ip:
            return "Skipped as no changes for DomainRecord"
        remote_record = self.fetch_remote_record(domain, sub_domain, type)

        if not remote_record:
            raise Exception("Failed finding remote DomainRecord {sub_domain}.{domain}]")

        if ip == remote_record.value:
            return "Skipped as we already updated DomainRecord {sub_domain}.{domain}]"

        # if we can fetch remote record and record's value doesn't equal to public IP
        sync_result = self.resolver.update_domain_record(remote_record.recordid, rr=remote_record.rr, record_value=ip,
                                                         record_type=type)

        if not sync_result:
            raise Exception("Failed updating DomainRecord {sub_domain}.{domain}]")
        else:
            return "Successfully updated DomainRecord {sub_domain}.{domain}]"

    def fetch_remote_record(self, domain, sub_domain, type="A"):
        fuzzy_matched_list = self.resolver.describe_domain_records(domain, rr_keyword=sub_domain, type_keyword=type)
        if not fuzzy_matched_list:
            raise Exception("Failed to fetch remote DomainRecords.")
            return None

        exact_matched_list = []
        check_keys = ('DomainName', 'RR', 'Type')
        local_record = {'DomainName': domain, 'RR': sub_domain, 'Type': type}
        for rec in fuzzy_matched_list:
            if all(rec.get(key, None) == local_record.get(key) for key in check_keys):
                exact_matched_list.append(rec)

        if not exact_matched_list:
            return None

        if len(exact_matched_list) > 1:
            DDNSUtils.err("Duplicate DomainRecord in Aliyun: {rec.RR}.{rec.DomainName}".format(rec=local_record))
            return None

        try:
            remote_record = RemoteDomainRecord(exact_matched_list[0])
        except Exception as ex:
            raise ex

        return remote_record


if __name__ == '__main__':
    serverAddress = ('', 8080)
    server = HTTPServer(serverAddress, RequestHandler)
    server.serve_forever()
