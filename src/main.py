import boto3
import certbot.main
import os
import shutil
import json
import urllib.request
from botocore.exceptions import ClientError
from acme import messages
import jsonschema

schema = {
    'definitions': {},
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'type': 'object',
    'required': [
        'domains',
        'is_production',
        'bucket',
        'email',
    ],
    'properties': {
        'domains': {
            'type': 'array',
            'items': {
                'type': 'string'
            }
        },
        'is_production': {
            'type': 'boolean'
        },
        'bucket': {
            'type': 'string'
        },
        'email': {
            'type': 'string'
        },
        'slack': {
            'type': 'object',
            'required': [
                'webhook',
                'channel'
            ],
            'properties': {
                'webhook': {
                    'type': 'string'
                },
                'channel': {
                    'type': 'string'
                },
                'icon_emoji': {
                    'type': 'string'
                },
                'username': {
                    'type': 'string'
                },
            }
        }
    }
}


def load_cert(domains):
    first_domain_name = domains[0].replace('*.', '', 1)

    path = '/tmp/config-dir/live/' + first_domain_name
    return {
        'domains': domains,
        'certificate': read_file(path + '/cert.pem'),
        'private_key': read_file(path + '/privkey.pem'),
        'certificate_chain': read_file(path + '/chain.pem'),
        'certificate_fullchain': read_file(path + '/fullchain.pem')
    }


def read_file(path):
    with open(path, 'r') as file:
        return file.read()


def provision_cert(domains, is_production, email):
    input_array = [
        'certonly',
        '-n',
        '--agree-tos',
        '--email', email,
        '--dns-route53',
        '-d', ','.join(domains),
        '--config-dir', '/tmp/config-dir/',
        '--work-dir', '/tmp/work-dir/',
        '--logs-dir', '/tmp/logs-dir/'
    ]

    if is_production:
        input_array.append('--server')
        input_array.append('https://acme-v02.api.letsencrypt.org/directory')
    else:
        input_array.append('--staging')

    certbot.main.main(input_array)
    return load_cert(domains)


def upload_cert_to_s3(cert, bucket_name, is_production):
    s3_urls = []
    for domain in cert['domains']:
        normalized_domain_name = domain.replace('*.', 'asterisk.', 1)

        path = normalized_domain_name

        if not is_production:
            path += '/staging'

        s3 = boto3.resource('s3')
        bucket = s3.Bucket(bucket_name)

        bucket.put_object(Key=path+'/privkey.pem',
                          Body=cert['private_key'])

        bucket.put_object(Key=path+'/cert.pem',
                          Body=cert['certificate'])

        bucket.put_object(Key=path+'/chain.pem',
                          Body=cert['certificate_chain'])

        bucket.put_object(Key=path+'/fullchain.pem',
                          Body=cert['certificate_fullchain'])

        s3_urls.append('https://s3.console.aws.amazon.com/s3/buckets/' +
                       bucket_name + '/' + path + '/')
    return s3_urls


def clear_work_dir():
    if os.path.exists('/tmp/config-dir'):
        shutil.rmtree('/tmp/config-dir')
    if os.path.exists('/tmp/work-dir'):
        shutil.rmtree('/tmp/work-dir')
    if os.path.exists('/tmp/logs-dir'):
        shutil.rmtree('/tmp/logs-dir')


def post_to_slack(slack, text):
    payload = {
        'username': slack.get('username', 'CertUpdater'),
        'icon_emoji': slack.get('icon_emoji', ':letsencrypt:'),
        'text': text,
        'channel': slack['channel']
    }

    json_data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        slack['webhook'], data=json_data, method='POST'
    )
    with urllib.request.urlopen(request) as response:
        return response.read().decode('utf-8')


def validate_bucket_name(bucket_name):
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)
    bucket.put_object(Key='tmp', Body='')
    response = bucket.delete_objects(
        Delete={
            'Objects': [
                {
                    'Key': 'tmp'
                },
            ]
        }
    )

    return response


def send_logs(text, slack=None):
    print(text)
    if slack is not None:
        post_to_slack(slack, text)


def handler(event, context):
    clear_work_dir()

    slack = None

    try:

        jsonschema.validate(event, schema)

        domains = event.get('domains')
        is_production = event.get('is_production')
        bucket_name = event.get('bucket')
        email = event.get('email')
        slack = event.get('slack')

        if is_production:
            stage = 'production'
        else:
            stage = 'staging'

        start_text = f'Updating {stage} certificates: {str(domains)}'
        send_logs(start_text, slack)

        validate_bucket_name(bucket_name)

        cert = provision_cert(domains, is_production, email)

        s3_urls = upload_cert_to_s3(cert, bucket_name, is_production)

        end_text = 'Finished uploading to S3:\n' + '\n'.join(s3_urls)
        send_logs(end_text, slack)
        return end_text

    # input
    except jsonschema.exceptions.ValidationError as e:
        error_message = '[failed] ' + str(e.message)
        send_logs(error_message, slack)
        raise Exception(error_message)

    # boto
    except ClientError as e:
        error_message = '[failed] ' + e.response['Error']['Message'] + ': ' + \
            bucket_name
        send_logs(error_message, slack)
        raise Exception(error_message)

    # rate limit
    except messages.Error as e:
        error_message = '[failed] ' + str(e)
        send_logs(error_message, slack)
        raise Exception(error_message)

    # certbot
    except certbot.errors.Error as e:
        error_message = '[failed] ' + str(e)
        send_logs(error_message, slack)
        raise Exception(error_message)
