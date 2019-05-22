from qcfractal.storage_sockets import storage_socket_factory
from qcfractal.storage_sockets.me_models import MoleculeORM, KeywordsORM, KVStoreORM, ResultORM
from qcfractal.storage_sockets.sql_models import MoleculeMap, KeywordsMap, KVStoreMap, ResultMap
from qcfractal.interface.models import KeywordSet, ResultRecord


sql_uri = "postgresql+psycopg2://qcarchive:mypass@localhost:5432/qcarchivedb"
mongo_uri = "mongodb://localhost:27017"
mongo_db_name = "qcf_compute_server_test"

MAX_LIMIT = 100
mongo_storage = storage_socket_factory(mongo_uri, mongo_db_name, db_type="mongoengine",
                                       max_limit=MAX_LIMIT)

sql_storage = storage_socket_factory(sql_uri, 'qcarchivedb', db_type='sqlalchemy',
                                     max_limit=MAX_LIMIT)

m_limit = mongo_storage.get_limit(MAX_LIMIT)
print("mongo limit: ", m_limit)

s_limit = sql_storage.get_limit(MAX_LIMIT)  #_max_limit
print("sql limit: ", s_limit)


def copy_molecules(with_check=False):
    """Copy from mongo to sql"""

    total_count = mongo_storage.get_total_count(MoleculeORM)
    print('Total # of Molecules in the DB is: ', total_count)

    for skip in range(0, total_count, m_limit):

        print('\nCurrent skip={}\n-----------'.format(skip))
        ret = mongo_storage.get_molecules(limit=m_limit, skip=skip)
        mongo_res = ret['data']
        print('mongo mol returned: ', len(mongo_res), ', total: ', ret['meta']['n_found'])

        # check if this patch has been already stored
        with sql_storage.session_scope() as session:
            if session.query(MoleculeMap).filter_by(mongo_id=mongo_res[-1].id).count() > 0:
                print('Skipping first ', skip+m_limit)
                continue

        sql_insered = sql_storage.add_molecules(mongo_res)['data']
        print('Inserted in SQL:', len(sql_insered))

        if with_check:
            ret = sql_storage.get_molecules(limit=m_limit, skip=skip)
            print('Get from SQL: n_found={}, returned={}'.format(ret['meta']['n_found'], len(ret['data'])))

            assert mongo_res[0].compare(ret['data'][0])

        # store the ids mapping in the sql DB
        with sql_storage.session_scope() as session:
            obj_map = []
            for mongo_obj, sql_id in zip(mongo_res, sql_insered):
                obj_map.append(MoleculeMap(sql_id=sql_id, mongo_id=mongo_obj.id))

            session.add_all(obj_map)
            session.commit()

    print('---- Done copying molecules\n\n')


def copy_keywords(with_check=False):
    """Copy from mongo to sql"""

    mongo_storage.add_keywords([KeywordSet(values={'key': 'test data'})])

    total_count = mongo_storage.get_total_count(KeywordsORM)
    print('Total # of Keywords in the DB is: ', total_count)

    for skip in range(0, total_count, m_limit):

        print('\nCurrent skip={}\n-----------'.format(skip))
        ret = mongo_storage.get_keywords(limit=m_limit, skip=skip)
        mongo_res= ret['data']
        print('mongo results returned: ', len(mongo_res), ', total: ', ret['meta']['n_found'])

        # check if this patch has been already stored
        with sql_storage.session_scope() as session:
            if session.query(KeywordsMap).filter_by(mongo_id=mongo_res[-1].id).count() > 0:
                print('Skipping first ', skip+m_limit)
                continue

        sql_insered = sql_storage.add_keywords(mongo_res)['data']
        print('Inserted in SQL:', len(sql_insered))

        if with_check:
            ret = sql_storage.get_keywords(limit=m_limit, skip=skip)
            print('Get from SQL: n_found={}, returned={}'.format(ret['meta']['n_found'], len(ret['data'])))

            assert mongo_res[0].hash_index == ret['data'][0].hash_index

        # store the ids mapping in the sql DB
        with sql_storage.session_scope() as session:
            obj_map = []
            for mongo_obj, sql_id in zip(mongo_res, sql_insered):
                obj_map.append(KeywordsMap(sql_id=sql_id, mongo_id=mongo_obj.id))

            session.add_all(obj_map)
            session.commit()

    print('---- Done copying keywords\n\n')


def copy_kv_store(with_check=False):
    """Copy from mongo to sql"""

    total_count = mongo_storage.get_total_count(KVStoreORM)
    print('Total # of KV_store in the DB is: ', total_count)

    for skip in range(0, total_count, m_limit):

        print('\nCurrent skip={}\n-----------'.format(skip))
        ret = mongo_storage.get_kvstore(limit=m_limit, skip=skip)
        mongo_res= ret['data']
        print('mongo kv_store returned: ', len(mongo_res), ', total: ', ret['meta']['n_found'])

        ids = list(mongo_res.keys())
        values = mongo_res.values()
        # check if this patch has been already stored
        with sql_storage.session_scope() as session:
            if session.query(KVStoreMap).filter_by(mongo_id=ids[-1]).count() > 0:
                print('Skipping first ', skip+m_limit)
                continue

        sql_insered = sql_storage.add_kvstore(values)['data']
        print('Inserted in SQL:', len(sql_insered))

        if with_check:
            ret = sql_storage.get_kvstore(limit=m_limit, skip=skip)
            print('Get from SQL: n_found={}, returned={}'.format(ret['meta']['n_found'], len(ret['data'])))

            assert list(values)[0] == list(ret['data'].values())[0]

        # store the ids mapping in the sql DB
        with sql_storage.session_scope() as session:
            obj_map = []
            for mongo_id, sql_id in zip(ids, sql_insered):
                obj_map.append(KVStoreMap(sql_id=sql_id, mongo_id=mongo_id))

            session.add_all(obj_map)
            session.commit()

    print('---- Done copying KV_store\n\n')


def copy_results(with_check=False):
    """Copy from mongo to sql"""

    total_count = mongo_storage.get_total_count(ResultORM)
    print('Total # of Results in the DB is: ', total_count)

    for skip in range(0, total_count, m_limit):

        print('\nCurrent skip={}\n-----------'.format(skip))
        ret = mongo_storage.get_results(limit=m_limit, skip=skip)
        mongo_res= ret['data']
        print('mongo results returned: ', len(mongo_res), ', total: ', ret['meta']['n_found'])

        # check if this patch has been already stored
        with sql_storage.session_scope() as session:
            if session.query(ResultMap).filter_by(mongo_id=mongo_res[-1]['id']).count() > 0:
                print('Skipping first ', skip+m_limit)
                continue

        # load mapped ids in memory
        mol_map, keywords_map, kv_store_map = [], [], []
        for res in mongo_res:
            if 'molecule' in res and res['molecule']:
                mol_map.append(res['molecule'])
            if 'keywords' in res and res['keywords']:
                keywords_map.append(res['keywords'])
            if 'stdout' in res and res['stdout']:
                kv_store_map.append(res['stdout'])
            if 'stderr' in res and res['stderr']:
                kv_store_map.append(res['stderr'])
            if 'error' in res and res['error']:
                kv_store_map.append(res['error'])

        with sql_storage.session_scope() as session:
            mols = session.query(MoleculeMap).filter(MoleculeMap.mongo_id.in_(mol_map)).all()
            mol_map = {i.mongo_id:i.sql_id for i in mols}

            keys = session.query(KeywordsMap).filter(KeywordsMap.mongo_id.in_(keywords_map)).all()
            keywords_map = {i.mongo_id: i.sql_id for i in keys}

            kv = session.query(KVStoreMap).filter(KVStoreMap.mongo_id.in_(kv_store_map)).all()
            kv_store_map = {i.mongo_id: i.sql_id for i in kv}

        # replace mongo ids Results with sql
        for res in mongo_res:
            res['molecule'] = mol_map[res['molecule']]
            if 'keywords' in res and res['keywords']:
                res['keywords'] = keywords_map[res['keywords']]
            if 'stdout' in res and res['stdout']:
                res['stdout'] = kv_store_map[res['stdout']]
            if 'stderr' in res and res['stderr']:
                res['stderr'] = kv_store_map[res['stderr']]
            if 'error' in res and res['error']:
                res['error'] = kv_store_map[res['error']]

        results_py = [ResultRecord(**res) for res in mongo_res]
        sql_insered = sql_storage.add_results(results_py)['data']
        print('Inserted in SQL:', len(sql_insered))

        if with_check:
            ret = sql_storage.get_results(limit=m_limit, skip=skip)
            print('Get from SQL: n_found={}, returned={}'.format(ret['meta']['n_found'], len(ret['data'])))

            assert mongo_res[0].compare(ret['data'][0])

        # store the ids mapping in the sql DB
        with sql_storage.session_scope() as session:
            obj_map = []
            for mongo_obj, sql_id in zip(mongo_res, sql_insered):
                obj_map.append(ResultMap(sql_id=sql_id, mongo_id=mongo_obj['id']))

            session.add_all(obj_map)
            session.commit()

if __name__ == "__main__":

    # sql_storage._clear_db('qcarchivedb')
    # copy_molecules(with_check=True)
    # copy_keywords(with_check=True)
    # copy_kv_store(with_check=True)
    copy_results(with_check=False)