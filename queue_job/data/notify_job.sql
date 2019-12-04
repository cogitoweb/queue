    CREATE OR REPLACE LANGUAGE plpython2u;

    CREATE OR REPLACE FUNCTION public.notify_job(base_url character varying, dbname character varying, uuid character varying)
        RETURNS text AS
    $BODY$
            import urllib2

            try:
                uri_to_call = "%s/queue_job/notifyjob?db=%s&job_uuid=%s" % (base_url, dbname, uuid)
                data = urllib2.urlopen(uri_to_call, timeout = 10)
            except:
                raise

            return data.read()
    $BODY$
        LANGUAGE plpython2u VOLATILE
        COST 1;

    GRANT EXECUTE ON FUNCTION public.notify_job(character varying, character varying, character varying) TO public;