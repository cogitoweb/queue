    CREATE OR REPLACE LANGUAGE plpython2u;

    CREATE OR REPLACE FUNCTION public.notify_job(dbname character varying, uuid character varying)
        RETURNS text AS
    $BODY$
            import urllib2

            try:
                uri_to_call = "http://localhost/queue_job/notifyjob?db=%&job_uuid=%s" % (dbname, uuid)
                data = urllib2.urlopen(uri_to_call, timeout = 10)
            except:
                raise

            return data.read()
    $BODY$
        LANGUAGE plpython2u VOLATILE
        COST 1;

    GRANT EXECUTE ON FUNCTION public.notify_job(dbname character varying, joibuid character varying) TO public;