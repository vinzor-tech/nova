REST API Version History
========================

This documents the changes made to the REST API with every
microversion change. The description for each version should be a
verbose one which has enough information to be suitable for use in
user documentation.

2.1
---

  This is the initial version of the v2.1 API which supports
  microversions. The V2.1 API is from the REST API users's point of
  view exactly the same as v2.0 except with strong input validation.

  A user can specify a header in the API request::

    X-OpenStack-Nova-API-Version: <version>

  where ``<version>`` is any valid api version for this API.

  If no version is specified then the API will behave as if a version
  request of v2.1 was requested.

2.2
---

  Added Keypair type.

  A user can request the creation of a certain 'type' of keypair (``ssh`` or ``x509``)
  in the ``os-keypairs`` plugin

  If no keypair type is specified, then the default ``ssh`` type of keypair is
  created.

  Fixes status code for ``os-keypairs`` create method from 200 to 201

  Fixes status code for ``os-keypairs`` delete method from 202 to 204

2.3 (Maximum in Kilo)
---------------------

  Exposed additional attributes in ``os-extended-server-attributes``:
  ``reservation_id``, ``launch_index``, ``ramdisk_id``, ``kernel_id``, ``hostname``,
  ``root_device_name``, ``userdata``.

  Exposed ``delete_on_termination`` for ``volumes_attached`` in ``os-extended-volumes``.

  This change is required for the extraction of EC2 API into a standalone
  service. It exposes necessary properties absent in public nova APIs yet.
  Add info for Standalone EC2 API to cut access to Nova DB.

2.4
---

  Show the ``reserved`` status on a ``FixedIP`` object in the ``os-fixed-ips`` API
  extension. The extension allows one to ``reserve`` and ``unreserve`` a fixed IP
  but the show method does not report the current status.

2.5
---

  Before version 2.5, the command ``nova list --ip6 xxx`` returns all servers
  for non-admins, as the filter option is silently discarded. There is no
  reason to treat ip6 different from ip, though, so we just add this
  option to the allowed list.

2.6
---

  A new API for getting remote console is added::

    POST /servers/<uuid>/remote-consoles
    {
      "remote_console": {
        "protocol": ["vnc"|"rdp"|"serial"|"spice"],
        "type": ["novnc"|"xpvnc"|"rdp-html5"|"spice-html5"|"serial"]
      }
    }

  Example response::

    {
      "remote_console": {
        "protocol": "vnc",
        "type": "novnc",
        "url": "http://example.com:6080/vnc_auto.html?token=XYZ"
      }
    }

  The old APIs 'os-getVNCConsole', 'os-getSPICEConsole', 'os-getSerialConsole'
  and 'os-getRDPConsole' are removed.

2.7
---

  Check the ``is_public`` attribute of a flavor before adding tenant access
  to it. Reject the request with HTTPConflict error.

2.8
---
  Add 'mks' protocol and 'webmks' type for remote consoles.

2.9
---

  Add a new ``locked`` attribute to the detailed view of
  servers. ``locked`` will be ``true`` if anyone is currently holding
  a lock on the server, ``false`` otherwise.

2.10
----

  Added user_id parameter to os-keypairs plugin, as well as a new property
  in the request body, for the create operation.

  Administrators will be able to list, get details and delete keypairs owned by
  users other than themselves and to create new keypairs on behalf of their
  users.

2.11
----

  Exposed attribute ``forced_down`` for ``os-services``.
  Added ability to change the ``forced_down`` attribute by calling an update.

2.12 (Maximum in Liberty)
-------------------------

  Exposes VIF ``net_id`` attribute in ``os-virtual-interfaces``.
  User will be able to get Virtual Interfaces ``net_id`` in Virtual Interfaces
  list and can determine in which network a Virtual Interface is plugged into.

2.13
----

  Add information ``project_id`` and ``user_id`` to ``os-server-groups``
  API response data.

2.14
----

  Remove ``onSharedStorage`` parameter from server's evacuate action. Nova will
  automatically detect if the instance is on shared storage.
  Also adminPass is removed from the response body. The user can get the
  password with the server's os-server-password action.

2.15
----

  From this version of the API users can choose 'soft-affinity' and
  'soft-anti-affinity' rules too for server-groups.

2.16
----

  Exposes new host_status attribute for servers/detail and servers/{server_id}.
  Ability to get nova-compute status when querying servers. By default, this is
  only exposed to cloud administrators.

2.17
----

  Add a new API for triggering crash dump in an instance. Different operation
  systems in instance may need different configurations to trigger crash dump.

2.18
----
  Establishes a set of routes that makes project_id an optional construct in v2.1.

2.19
----
  Allow the user to set and get the server description.
  The user will be able to set the description when creating, rebuilding,
  or updating a server, and get the description as part of the server details.

2.20
----
  From this version of the API user can call detach and attach volumes for
  instances which are in shelved and shelved_offloaded state.

2.21
----

  The ``os-instance-actions`` API now returns information from deleted
  instances.

2.22
----

  A new resource servers:migrations added. A new API to force live migration
  to complete added::

    POST /servers/<uuid>/migrations/<id>/action
    {
      "force_complete": null
    }

2.23
----

  From this version of the API users can get the migration summary list by
  index API or the information of a specific migration by get API.
  And the old top-level resource `/os-migrations` won't be extended anymore.
  Add migration_type for old /os-migrations API, also add ref link to the
  /servers/{uuid}/migrations/{id} for it when the migration is an in-progress
  live-migration.

2.24
----

  A new API call to cancel a running live migration::

    DELETE /servers/<uuid>/migrations/<id>

2.25 (Maximum in Mitaka)
------------------------

  Modify input parameter for ``os-migrateLive``. The block_migration will
  support 'auto' value, and disk_over_commit flag will be removed.
