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
    'bucket',
    'email',
    'slack',
    'isProd'
  ],
  'properties': {
    'domains': {
      'type': 'array',
      'items': {
        'type': 'string'
      }
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
        }
      }
    },
    'isProd': {
      'type': 'boolean'
    }
  }
}


def load_cert(domain):
    domain_name = domain.replace('*.', '', 1)

    path = '/tmp/config-dir/live/' + domain_name
    return {
      'certificate': read_file(path + '/cert.pem'),
      'private_key': read_file(path + '/privkey.pem'),
      'certificate_chain': read_file(path + '/chain.pem'),
      'certificate_fullchain': read_file(path + '/fullchain.pem')
    }


def read_file(path):
    with open(path, 'r') as file:
        return file.read()


def provision_cert(isProd, domains, email):
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

    if isProd:
        input_array.append('--server')
        input_array.append('https://acme-v02.api.letsencrypt.org/directory')
    else:
        input_array.append('--staging')

    certbot.main.main(input_array)
    return load_cert(domains[0])


def upload_cert_to_s3(cert, domains, bucket_name):
    s3_urls = []
    for domain in domains:
        domain_name = domain.replace('*.', 'asterisk.', 1)

        s3 = boto3.resource('s3')
        bucket = s3.Bucket(bucket_name)

        bucket.put_object(Key=domain_name+'/privkey.pem',
                          Body=cert['private_key'])

        bucket.put_object(Key=domain_name+'/cert.pem',
                          Body=cert['certificate'])

        bucket.put_object(Key=domain_name+'/chain.pem',
                          Body=cert['certificate_chain'])

        bucket.put_object(Key=domain_name+'/fullchain.pem',
                          Body=cert['certificate_fullchain'])

        s3_urls.append('https://s3.console.aws.amazon.com/s3/buckets/' +
                       bucket_name + '/' + domain_name + '/')
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
                'username': 'CertUpdater',
                'icon_emoji': ':letsencrypt:',
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


def handler(event, context):
    clear_work_dir()

    try:

        jsonschema.validate(event, schema)

        domains = event['domains']
        bucket_name = event['bucket']
        isProd = event['isProd']
        slack = event['slack']
        email = event['email']

        if isProd:
            stage = 'production'
        else:
            stage = 'staging'

        start_text = f'Updating {stage} certificates: {str(domains)}'
        print(start_text)
        post_to_slack(slack, start_text)

        validate_bucket_name(bucket_name)

        cert = provision_cert(isProd, domains, email)

        s3_urls = upload_cert_to_s3(cert, domains, bucket_name)

        end_text = 'Finished uploading to S3:\n' + '\n'.join(s3_urls)
        post_to_slack(slack, end_text)
        return end_text

    # input
    except jsonschema.exceptions.ValidationError as e:
        error_message = '[failed] ' + str(e.message)
        post_to_slack(slack, error_message)
        return error_message

    # boto
    except ClientError as e:
        error_message = '[failed] ' + e.response['Error']['Message'] + ': ' + \
                      bucket_name
        post_to_slack(slack, error_message)
        return error_message

    # rate limit
    except messages.Error as e:
        error_message = '[failed] ' + str(e)
        post_to_slack(slack, error_message)
        return error_message

    # certbot
    except certbot.errors.Error as e:
        error_message = '[failed] ' + str(e)
        post_to_slack(slack, error_message)
        return error_message
