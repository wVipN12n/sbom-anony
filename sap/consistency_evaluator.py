import csv
import json
import os
import re
import math
from loguru import logger
from Levenshtein import distance, jaro
from urllib.parse import unquote
import semver
from packageurl import PackageURL
# for debug
fileinvalid = 0
varchar = 0
backspace = 0
VersionNotMatch = 0
NoneOrEmpty = 0
SpecialChar = 0
ManualVersion = 0
# for usage
TotalMatchedVersion = 0
TotalMatchedName = 0


def check_empty(v):
    return v == 'NONE' or v == 'NOASSERTION' or v is None


def equal_cmp(v1, v2):
    if check_empty(v1) and check_empty(v2) or v1 == '' and v2 == '':
        return 0
    if v1 == 'NE' or v2 == 'NE' or check_empty(v1) or check_empty(v2) or v1 == '' or v2 == '':
        return 0
    if v1.lower() == v2.lower():
        return 1
    else:
        return 0


def check_digit(version):
    return all(char.isdigit() or char == '.' for char in version) and version != ''


def deal_filename(name):
    if name.startswith('./'):
        name = name[2:]
    elif name.startswith('/'):
        name = name[1:]
    return name


def compareName(name1, name2):
    name1, name2 = unquote(name1), unquote(name2)
    name1 = re.sub("npm:|pip:|go:|actions:|composer:|rust:|ruby:|nuget:|rubygems:|docker:|maven:| ", '', name1).lower()
    name2 = re.sub("npm:|pip:|go:|actions:|composer:|rust:|ruby:|nuget:|rubygems:|docker:|maven:| ", '', name2).lower()
    if '15.4.6' in name1 or '15.4.6' in name2:
        logger.info(f'[ManualDefinedName]: {name1}||{name2}')
    return equal_cmp(name1, name2)


def purl_consistency(p1, p2):
    if p1 == p2:
        return 1.
    if p1 == 'NE' or p2 == 'NE':
        return 0.
    if check_empty(p1) or check_empty(p2):
        return 0.
    try:
        p1_dict = PackageURL.from_string(p1).to_dict()
        p2_dict = PackageURL.from_string(p2).to_dict()
    except Exception as e:
        logger.error(f'Invalid purl: {p1}||{p2}')
        return jaro(p1.lower(), p2.lower())
    none_zero_count_p1 = sum(1 for x in p1_dict.values() if x != None)
    none_zero_count_p2 = sum(1 for x in p2_dict.values() if x != None)
    weight = max(none_zero_count_p1, none_zero_count_p2)
    weight = 1. / weight if weight > 0 else 0.
    score = 0
    try:
        for key in p1_dict.keys():
            if key == 'version':
                score += version_consistency(p1_dict[key] if p1_dict[key] != None else '', p2_dict[key] if p2_dict[key] != None else '')
            else:
                score += jaro(str(p1_dict[key]).lower() if p1_dict[key] != None else '', str(p2_dict[key]).lower() if p2_dict[key] != None else '')
            score *= weight
    except Exception as e:
        logger.error(f'purl: {p1}||{p2}')
        return jaro(p1.lower(), p2.lower())
    return score


def longest_common_substring_consistency_score(str1, str2):
    if check_empty(str1) and check_empty(str2) or str1 == '' and str2 == '':
        return 0
    if str1 == 'NE' or str2 == 'NE' or check_empty(str1) or check_empty(str2) or str1 == '' or str2 == '':
        return 0.
    if str1 == str2:
        return 1.
    if type(str1) != str or type(str2) != str:
        logger.error(f'Invalid string: {str1}||{str2}')

    str1, str2 = unquote(str1), unquote(str2)  # fix encoding problem
    # Create a 2D array to store lengths of longest common suffixes
    dp = [[0] * (len(str2) + 1) for _ in range(len(str1) + 1)]
    longest_len = 0
    end_pos = 0

    # Build the dp table and find the longest length
    for i in range(1, len(str1) + 1):
        for j in range(1, len(str2) + 1):
            if str1[i-1] == str2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
                if dp[i][j] > longest_len:
                    longest_len = dp[i][j]
                    end_pos = i
            else:
                dp[i][j] = 0

    # Extract the longest common substring
    # longest_common_substr = str1[end_pos-longest_len:end_pos]
    consistency_score = longest_len / max(len(str1), len(str2)) if max(len(str1), len(str2)) else 0.
    return consistency_score


def version_consistency(version1, version2):
    global SpecialChar, fileinvalid, varchar, backspace, VersionNotMatch, NoneOrEmpty, ManualVersion
    if check_empty(version1) and check_empty(version2):  # FIXME
        # logger.error(f'[EmptyVersionValue]: {version1}||{version2}')
        return 0
    if check_empty(version1) or check_empty(version2) or version1 == 'NE' or version2 == 'NE':  # FIXME
        return 0.
    if version1.lower() == version2.lower():
        return 1.
    if version1 == "" or version2 == "":
        return 0.
    if '15.4.6' in version1 or '15.4.6' in version2:
        logger.info(f'[ManualDefinedVersion]: {version1}||{version2}')
        ManualVersion += 1
        return 0.  # manually defined version in repo
    weights = [0.7, 0.2, 0.1]

    version1 = version1.strip().replace(' ', '')
    version2 = version2.strip().replace(' ', '')
    if version1.startswith('v') or version1.startswith('V'):
        version1 = version1[1:]
    if version2.startswith('v') or version2.startswith('V'):
        version2 = version2[1:]

    if version1.lower() == version2.lower():
        return 1.

    score = 0
    special = ['<', '>', '=', '+', ',', '~', '!', '-']
    for sp in special:
        if sp in version1 or sp in version2:
            SpecialChar += 1
            logger.info(f'[SpecialChar]: {version1}||{version2}')
            break
    try:
        if semver.Version.is_valid(version1) and semver.Version.is_valid(version2):
            semver_version1 = semver.Version(version1)
            semver_version2 = semver.Version(version2)
            count_1 = 0
            count_2 = 0
            for i in semver_version1:
                if i != None:
                    count_1 += 1
            for i in semver_version2:
                if i != None:
                    count_2 += 1
            count = min(count_1, count_2)
            if count == 4:
                weights = [0.6, 0.2, 0.1, 0.1]
            elif count == 5:
                weights = [0.5, 0.2, 0.15, 0.1, 0.05]
            for i in range(count):
                jaro_score = jaro(semver_version1[i], semver_version2[i])
                score += jaro_score*weights[i]
                if score == 1.0:
                    return 1.
                if jaro_score != 1.0:
                    break
            return score
    except Exception as e:
        pass

    v1_parts = version1.split('.')
    v2_parts = version2.split('.')
    length = min(len(v1_parts), len(v2_parts))
    if length == 2:
        weights = [0.8, 0.2]
    if length == 1:
        weights = [1.]
    length = length if length <= 3 else 3
    diffs = [0., 0., 0.]
    for i in range(length):
        run_flag = False
        if i == 0:
            run_flag = True
        elif diffs[i-1] == weights[i-1]:
            run_flag = True
        if run_flag:
            if v1_parts[i] == v2_parts[i]:
                diffs[i] = weights[i]
            elif (check_digit(v1_parts[i]) and check_digit(v2_parts[i])):
                diffs[i] = math.fabs(int(v1_parts[i]) - int(v2_parts[i])) / max(int(v1_parts[i]), int(v2_parts[i])) * weights[i]
            else:
                diffs[i] = jaro(v1_parts[i].lower(), v2_parts[i].lower()) * weights[i]
    return sum(diffs)


def is_valid_json(file_path):
    if not os.path.exists(file_path):
        return False
    try:
        with open(file_path, 'r') as f:
            json.load(f)
        return True
    except json.JSONDecodeError:
        return False


def text_consistency(text1, text2):  # for author, originator, supplier, copyright, etc.
    if check_empty(text1) and check_empty(text2) or text1 == '' and text2 == '':
        # logger.error(f'[EmptyTextValue]: {text1}||{text2}')
        return 0
    if text1 == 'NE' or text2 == 'NE' or check_empty(text1) or check_empty(text2):
        return 0.
    else:
        if text1.lower() == text2.lower():
            return 1.
        return jaro(unquote(text1).lower(), unquote(text2).lower())


def deal_license(license):
    if license == 'NE' or license == '' or check_empty(license):
        return []
    if type(license) == str:
        license_list = license.split(' ')
        if len(license_list) > 1:
            if 'AND' in license_list:
                license_list.remove('AND')
            if 'OR' in license_list:
                license_list.remove('OR')
        return license_list
    elif type(license) == list:
        license_list = []
        for li in license:
            license_list += deal_license(li)
        return license_list
    elif type(license) == dict:
        if 'expression' in license:  # scancode
            license_list = license['expression'].split(' ')
            if len(license_list) > 1:
                if 'AND' in license_list:
                    license_list.remove('AND')
                if 'OR' in license_list:
                    license_list.remove('OR')
        elif 'license' in license:  # ort
            license_list = []
            for x in license['license']:
                if type(x) == str:
                    if x == 'id' or x == 'name':
                        license_list.append(license['license'][x])
                    continue
                if 'id' in x:
                    license_list.append(x['id'])
                elif 'name' in x:
                    license_list.append(x['name'])
        return license_list
    else:
        logger.error(f'Invalid license: {license}')
        return []


def license_consistency(license1, license2):
    if check_empty(license1) and check_empty(license2) or license1 == '' and license2 == '':
        return 0
    if license1 == 'NE' or license2 == 'NE' or check_empty(license1) or check_empty(license2) or license1 == '' or license2 == '':
        return 0.
    if license1 == license2:
        return 1.

    score = 0.
    length = 1
    license_list1 = deal_license(license1)
    license_list2 = deal_license(license2)
    if type(license_list1) != list or type(license_list2) != list:
        logger.error(f'Invalid license deal: {license1}||{license2}||{license_list1}||{license_list2}')

    if len(license_list1) == 0 or len(license_list2) == 0:
        return 0.
    for l1 in license_list1:
        for l2 in license_list2:
            score += int(l1 == l2)
    score /= max(len(license_list1), len(license_list2))
    return score


def cdx_consistency(file1_path, file2_path, result_path):
    filename1, tool1, reponame1, filedata1 = parse_fileinfo(file1_path)
    filename2, tool2, reponame2, filedata2 = parse_fileinfo(file2_path)
    metadata1, metadata2 = filedata1['metadata'], filedata2['metadata']
    component1, component2 = filedata1['components'], filedata2['components']
    cmp_flag = True
    if component1 == 'NE' or component2 == 'NE':
        cmp_flag = False
    else:
        component_keys1, component_keys2 = component1.keys(), component2.keys()
    all_matched_scores = {}
    all_matched_scores['basic_info'] = f'cdx_{tool1}_{tool2}_{reponame1}'
    if metadata1 == 'NE' or metadata2 == 'NE':
        all_matched_scores['repo_info'] = [0, 0]
    else:
        repo_name1 = metadata1['name_com']
        repo_name2 = metadata2['name_com']
        if check_empty(repo_name1) and check_empty(repo_name2) or repo_name1 == '' and repo_name2 == '':  # FIXME 4.1 fix
            repo_name_score = 0
        elif repo_name1 == 'NE' or repo_name2 == 'NE' or check_empty(repo_name1) or check_empty(repo_name2) or repo_name1 == '' or repo_name2 == '':  # FIXME
            repo_name_score = 0
        else:
            repo_name_score = jaro(repo_name1.lower(), repo_name2.lower())
        all_matched_scores['repo_info'] = [repo_name_score,
                                           version_consistency(metadata1['version_com'], metadata2['version_com'])]
    all_matched_scores['pkg_info'] = []
    all_matched_scores['statistic_info'] = []
    matched_pkg = []
    if not cmp_flag:
        all_matched_scores['statistic_info'] += [0, 0, 0]
        all_matched_scores['pkg_info'] = [[0, 0, 0, 0, 0, 0]]
        return all_matched_scores
    for k1 in component_keys1:
        pkg1 = component1[k1]
        for k2 in component_keys2:
            pkg2 = component2[k2]
            if compareName(pkg1['name'], pkg2['name']):
                if (pkg1['name']) in matched_pkg or pkg2['name'] in matched_pkg:
                    continue
                matched_pkg.append(pkg1['name'])
                author_score = text_consistency(pkg1['author'], pkg2['author'])

                type_score = equal_cmp(pkg1['type'], pkg2['type'])

                purl_score = purl_consistency(pkg1['purl'], pkg2['purl'])
                cpe_score = longest_common_substring_consistency_score(pkg1['cpe'], pkg2['cpe'])

                license_score = license_consistency(pkg1['licenses'], pkg2['licenses'])
                version_score = version_consistency(pkg1['version'], pkg2['version'])
                result = [author_score, type_score, purl_score, cpe_score, license_score, version_score]
                if any(x < 0 for x in result):
                    with open(f'{result_path}/cdx-special-consistency.csv', 'a') as fd:
                        writer = csv.writer(fd)
                        writer.writerow(['cdx', tool1, tool2, reponame1, pkg1['name']] + result)
                        all_matched_scores['pkg_info'].append([math.fabs(x) for x in result])
                else:
                    all_matched_scores['pkg_info'].append(result)

    if len(all_matched_scores['pkg_info']) == 0:
        all_matched_scores['pkg_info'].append([0, 0, 0, 0, 0, 0])

    all_matched_scores['statistic_info'] += [len(component_keys1), len(component_keys2), len(matched_pkg)]
    logger.success(f'[FinishedCDX]: {tool1}||{tool2}||{reponame1}')
    return all_matched_scores


def external_ref_proc(externalRefs: list) -> list:
    if isinstance(externalRefs, str):
        logger.error(f'[InvalidExternalRefs]: {externalRefs}')
        return [[], []]
    cpe_list = []
    purl_list = []
    for e in externalRefs:
        if isinstance(e, str):
            continue
        ref_type = e.get('referenceType', "NE")
        if 'cpe' in ref_type:
            cpe_list.append(e['referenceLocator'])
        elif 'purl' in ref_type:
            purl_list.append(e['referenceLocator'])
    return cpe_list, purl_list


def deal_PVC(PVC):
    if PVC == 'NE' or check_empty(PVC) or PVC == '':
        return None
    if type(PVC) == str:
        return PVC
    elif type(PVC) == list:
        if len(PVC) == 1:
            logger.info(f'[ListPVC]: {PVC}||{PVC[0]}')
            return PVC[0]
    elif type(PVC) == dict:
        if 'packageVerificationCodeValue' in PVC:
            return PVC['packageVerificationCodeValue']
    logger.error(f'Invalid packageVerificationCode: {PVC}')
    return None


def spdx_consistency(file1_path, file2_path, result_path):
    filename1, tool1, reponame1, filedata1 = parse_fileinfo(file1_path)
    filename2, tool2, reponame2, filedata2 = parse_fileinfo(file2_path)
    doc1, doc2 = filedata1['documents'], filedata2['documents']
    pkgs1, pkgs2 = filedata1['packages'], filedata2['packages']
    files1, files2 = filedata1['files'], filedata2['files']

    pkg_flag = True
    if pkgs1 == 'NE' or pkgs2 == 'NE':
        pkg_flag = False
    else:
        pkgs_keys1, pkgs_keys2 = pkgs1.keys(), pkgs2.keys()

    files_flag = True
    if files1 == 'NE' or files2 == 'NE':
        files_flag = False
    else:
        files_keys1, files_keys2 = files1.keys(), files2.keys()

    all_matched_scores = {}
    all_matched_scores['basic_info'] = f'spdx_{tool1}_{tool2}_{reponame1}'
    all_matched_scores['repo_info'] = []
    all_matched_scores['pkg_info'] = []
    all_matched_scores['files_info'] = []
    all_matched_scores['statistic_info'] = []

    repo1_flag = False
    repo2_flag = False
    if files_flag:
        matched_files = []
        for key1 in files_keys1:
            if len(files_keys1) > 2000 or len(files_keys2) > 2000:
                logger.warning(f'[TooManyFiles]: {tool1}||{tool2}||{reponame1}')
                break
            f1 = files1[key1]
            for f2 in files_keys2:
                f2 = files2[f2]
                if compareName(deal_filename(f1['name']), deal_filename(f2['name'])):
                    if f1['name'] in matched_files or f2['name'] in matched_files:
                        continue
                    matched_files.append(f1['name'])
                    if len(f1['checksums']) == 0 or len(f2['checksums']) == 0:
                        checksum_score = 0.

                    elif len(f1['checksums']) == 1 and len(f2['checksums']) == 1:
                        checksum_score = equal_cmp(f1['checksums'][0]['checksumValue'], f2['checksums'][0]['checksumValue'])
                        if checksum_score == 1:
                            print(f1['checksums'][0]['checksumValue'], f2['checksums'][0]['checksumValue'])
                        elif checksum_score == 0:
                            logger.error(
                                f'[InconsistentChecksum]: spdx||{tool1}||{tool2}||{reponame1}||{f1["name"]}||{f1["checksums"][0]["checksumValue"]}||{f2["checksums"][0]["checksumValue"]}')
                        elif checksum_score == -1:  # impossible
                            logger.error(
                                f'[SpecialChecksum]: spdx||{tool1}||{tool2}||{reponame1}||{f1["name"]}||{f1["checksums"][0]["checksumValue"]}||{f2["checksums"][0]["checksumValue"]}')
                            checksum_score = 1
                    else:
                        len1, len2 = len(f1['checksums']), len(f2['checksums'])
                        checksum_score = 0.
                        for c1 in f1['checksums']:
                            for c2 in f2['checksums']:
                                if c1['algorithm'] == c2['algorithm']:
                                    c = equal_cmp(c1['checksumValue'], c2['checksumValue'])
                                    if c == -1:  # impossible
                                        checksum_score += 1
                                        logger.error(
                                            f'[SpecialChecksum]: spdx||{tool1}||{tool2}||{reponame1}||{f1["name"]}||{c1["checksumValue"]}||{c2["checksumValue"]}')
                                    elif c == 0:
                                        checksum_score += 0
                                        logger.error(
                                            f'[InconsistentChecksum]: spdx||{tool1}||{tool2}||{reponame1}||{f1["name"]}||{c1["checksumValue"]}||{c2["checksumValue"]}')
                                    else:
                                        checksum_score += c
                                        logger.info(
                                            f'[SameChecksum]: spdx||{tool1}||{tool2}||{reponame1}||{f1["name"]}||{c1["checksumValue"]}||{c2["checksumValue"]}')

                        checksum_score /= max(len(f1['checksums']), len(f2['checksums']))
                    all_matched_scores['files_info'].append([checksum_score])

        if len(all_matched_scores['files_info']) == 0:
            all_matched_scores['files_info'].append([0])
        all_matched_scores['statistic_info'] += [len(files_keys1), len(files_keys2), len(matched_files)]

    if not files_flag:
        all_matched_scores['statistic_info'] += [0, 0, 0]
        all_matched_scores['files_info'] = [[0]]

    if not pkg_flag:
        all_matched_scores['statistic_info'] += [0, 0, 0]
        all_matched_scores['repo_info'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        all_matched_scores['pkg_info'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        return all_matched_scores

    matched_pkg = []
    for k1 in pkgs_keys1:
        pkg1 = pkgs1[k1]
        if compareName(pkg1['name'], reponame1):
            repo1_flag = True
        for k2 in pkgs_keys2:
            pkg2 = pkgs2[k2]
            if compareName(pkg2['name'], reponame1):
                repo2_flag = True
            if compareName(pkg1['name'], pkg2['name']):
                if pkg1['name'] in matched_pkg or pkg2['name'] in matched_pkg:
                    continue
                matched_pkg.append(pkg1['name'])

                originator_score = text_consistency(pkg1['originator'], pkg2['originator'])
                supplier_score = text_consistency(pkg1['supplier'], pkg2['supplier'])
                copyright_score = text_consistency(pkg1['copyrightText'], pkg2['copyrightText'])

                version_score = version_consistency(pkg1['versionInfo'], pkg2['versionInfo'])

                PVC_score = equal_cmp(deal_PVC(pkg1['packageVerificationCode']), deal_PVC(pkg2['packageVerificationCode']))  # 4.1已改正

                cpe1, purl1 = external_ref_proc(pkg1['externalRefs'])
                cpe2, purl2 = external_ref_proc(pkg2['externalRefs'])
                cpe_score, purl_score = 0., 0.
                neg_cpe, neg_purl = 0., 0.
                for c1 in cpe1:
                    for c2 in cpe2:
                        c = longest_common_substring_consistency_score(c1, c2)
                        if c == -1:  # impossible
                            neg_cpe += -1
                            cpe_score += 1
                            logger.error(f'[SpecialCPE]: spdx||{tool1}||{tool2}||{reponame1}||{pkg1["name"]}||{c1}||{c2}')
                        else:
                            cpe_score += longest_common_substring_consistency_score(c1, c2)
                cpe_score = cpe_score / max(len(cpe1), len(cpe2)) if max(len(cpe1), len(cpe2)) != 0 else 0
                for p1 in purl1:
                    for p2 in purl2:
                        p = purl_consistency(p1, p2)
                        if p == -1:  # impossible
                            neg_purl += -1
                            purl_score += 1
                            logger.error(f'[SpecialPURL]: spdx||{tool1}||{tool2}||{reponame1}||{pkg1["name"]}||{p1}||{p2}')
                        else:
                            purl_score += p
                purl_score = purl_score / max(len(purl1), len(purl2)) if max(len(purl1), len(purl2)) != 0 else 0

                dL_score = longest_common_substring_consistency_score(pkg1['downloadLocation'], pkg2['downloadLocation'])

                licenseC_score = license_consistency(pkg1['licenseConcluded'], pkg2['licenseConcluded'])
                licenseD_score = license_consistency(pkg1['licenseDeclared'], pkg2['licenseDeclared'])

                if repo1_flag and repo2_flag:
                    all_matched_scores['repo_info'] = [jaro(doc1['name'], doc2['name']), originator_score, supplier_score, copyright_score,
                                                       version_score, PVC_score, cpe_score, purl_score, dL_score, licenseC_score, licenseD_score]
                    repo1_flag = False
                    repo2_flag = False
                else:
                    result = [originator_score, supplier_score, copyright_score,
                              version_score, PVC_score, cpe_score, purl_score, dL_score, licenseC_score, licenseD_score]
                    if any(x < 0 for x in result + [neg_cpe, neg_purl]):
                        with open(f'{result_path}/spdx-special-consistency.csv', 'a') as fd:
                            writer = csv.writer(fd)
                            writer.writerow(['spdx', tool1, tool2, reponame1, pkg1['name']] + result + [neg_cpe, neg_purl])
                        all_matched_scores['pkg_info'].append([math.fabs(x) for x in result])
                    else:
                        all_matched_scores['pkg_info'].append(result)

    if len(all_matched_scores['pkg_info']) == 0:
        all_matched_scores['pkg_info'].append([0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    if len(all_matched_scores['repo_info']) == 0:
        all_matched_scores['repo_info'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    all_matched_scores['statistic_info'] += [len(pkgs_keys1), len(pkgs_keys2), len(matched_pkg)]
    logger.success(f'[FinishedSPDX]: {tool1}||{tool2}||{reponame1}')

    return all_matched_scores


def compare_files(file1_path, file2_path, standard, result_path):
    global fileinvalid, TotalMatchedName
    filevalidflag = True

    if file1_path == file2_path:
        logger.debug(f'[SameFile]: {file1_path}')
        filevalidflag = False
        fileinvalid += 1

    if not is_valid_json(file1_path):
        logger.debug(f'[FileNotExistOrInvalid]: {file1_path}')
        filevalidflag = False
        fileinvalid += 1

    if not is_valid_json(file2_path):
        logger.debug(f'[FileNotExistOrInvalid]: {file2_path}')
        filevalidflag = False
        fileinvalid += 1

    if not filevalidflag:
        return None

    if standard == 'spdx':
        all_matched_scores = spdx_consistency(file1_path, file2_path, result_path)
    elif standard == 'cdx':
        all_matched_scores = cdx_consistency(file1_path, file2_path, result_path)
    else:
        logger.error(f'Invalid standard: {standard}')

    return all_matched_scores


def parse_fileinfo(path):
    string = os.path.basename(path)
    filename = string[:string.rfind(".")]
    _, tool, reponame = filename.split('#')
    with open(path, 'r') as file:
        data = json.load(file)
    return filename, tool, reponame, data


def write_row2csv(filename: str, data: list) -> None:
    with open(filename, 'a') as f:
        writer = csv.writer(f)
        writer.writerow(data)


def run_consistency_evaluator(standard, result_path, filepath, repo_names):
    tools_spdx = ['syft', 'gh-sbom', 'ort', 'sbom-tool']
    tools_cdx = ['syft', 'gh-sbom', 'ort', 'scancode', 'cdxgen']
    # filepath = '/mnt/sbom-final-codes/results/field_extraction/'
    # filepath = '/mnt/sbom-final-codes/add_results/field_extraction/'
    # filepath = '/mnt/three-lans/parse_results/field_extraction-python/'
    result_path = os.path.join(result_path, 'consistency')
    if not os.path.exists(result_path):
        os.makedirs(result_path)

    special = os.path.join(result_path, f'{standard}-special-consistency.csv')
    with open(special, 'w', newline='') as fd:
        writer = csv.writer(fd)
        if standard == 'cdx':
            writer.writerow(['standard', 'tool1', 'tool2', 'repo_name', 'pkg_name',
                             'author_score', 'type_score', 'purl_score', 'cpe_score', 'license_score', 'version_score'])
        elif standard == 'spdx':
            # ['spdx', tool1, tool2, reponame1, pkg1['name']] + result + [neg_cpe, neg_purl]
            writer.writerow(['standard', 'tool1', 'tool2', 'repo_name', 'pkg_name',
                             # pkg
                             'originator_score', 'supplier_score', 'copyright_score', 'version_score', 'PVC_score', 'cpe_score',
                             'purl_score', 'dL_score', 'licenseC_score', 'licenseD_score', 'neg_cpe', 'neg_purl'])
    if standard == 'spdx':
        tools = tools_spdx
    elif standard == 'cdx':
        tools = tools_cdx
    for i in range(len(tools)):
        for j in range(i+1, len(tools)):
            tool1 = tools[i]
            tool2 = tools[j]
            wbfile = os.path.join(result_path, f'{standard}-{tool1}-{tool2}-package-consistency.csv')
            with open(wbfile, 'w', newline='') as fd:
                writer = csv.writer(fd)
                if standard == 'cdx':
                    writer.writerow(['repo_name', 'repo_name_meta', 'repo_version', 'comp_num1', 'comp_num2', 'matched_comps',
                                     'author_score', 'type_score', 'purl_score', 'cpe_score', 'license_score', 'version_score'])
                elif standard == 'spdx':
                    writer.writerow(['repo_name', 'files_num1', 'files_num2', 'matched_files', 'pkgs_num1', 'pkgs_num2', 'matched_pkgs',
                                    # repo
                                     'doc_name', 'originator_score_r', 'supplier_score_r', 'copyright_score_r', 'version_score_r',
                                     'PVC_score_r', 'cpe_score_r', 'purl_score_r', 'dL_score_r', 'licenseC_score_r', 'licenseD_score_r',
                                     # pkg
                                     'originator_score', 'supplier_score', 'copyright_score', 'version_score', 'PVC_score', 'cpe_score',
                                     'purl_score', 'dL_score', 'licenseC_score', 'licenseD_score',
                                     # files
                                     'checksum_score'])

    # with open('/mnt/github-python/github-python-names-sorted.txt', 'r') as fd:
    # with open('/mnt/additional_exp/small_repos_name.txt', 'r') as fd:
    with open(repo_names, 'r') as fd:
        line = fd.readline()
        while (line):
            line = line.strip()
            for i in range(len(tools)):
                tool1 = tools[i]
                filepath1 = os.path.join(filepath, f'{standard}#{tool1}#{line}.json')
                for j in range(i+1, len(tools)):
                    tool2 = tools[j]
                    filepath2 = os.path.join(filepath, f'{standard}#{tool2}#{line}.json')

                    results = compare_files(filepath1, filepath2, standard, result_path)
                    if results is not None:
                        if standard == 'cdx':
                            row = [line] + results['repo_info'] + results['statistic_info'] + \
                                [sum(x) / len(x) for x in zip(*results['pkg_info'])]
                        elif standard == 'spdx':
                            row = [line] + results['statistic_info'] + results['repo_info'] + \
                                [sum(x) / len(x) for x in zip(*results['pkg_info'])] + \
                                [sum(x) / len(x) for x in zip(*results['files_info'])]
                        wbfile = os.path.join(result_path, f'{standard}-{tool1}-{tool2}-package-consistency.csv')
                        write_row2csv(wbfile, row)
            line = fd.readline()
    return result_path
# spdx
# all_matched['pkg_info' or 'repo_info'] = originator_score, supplier_score, copyright_score, version_score, PVC_score,
#                                          cpe_score, purl_score, dL_score, licenseC_score, licenseD_score
# all_matched['files_info'] = f1['name'], checksum_score
# all_matched['statistic_info'] = [len(files_keys1), len(files_keys2), len(matched_files), len(pkgs_keys1), len(pkgs_keys2), len(matched_pkg)]

# cdx
# all_matched['repo_info'] = [name_com, version_com]
# all_matched['pkg_info'] = [author_score, type_score, purl_score, cpe_score, license_score, version_score]
# all_matched['statistic_info'] = [len(component_keys1), len(component_keys2), len(matched_pkg)]


if __name__ == '__main__':
    for lan in ['c-cpp', 'java', 'python']:
        path_result = f'/mnt/three-lans/parse_results/consistency_zero-{lan}'

        if not os.path.exists(path_result):
            os.makedirs(path_result)

        logger.add(f"/mnt/three-lans/parse_sboms-logs/package_consistency.zero-{lan}.log")
        filepath = f'/mnt/three-lans/parse_results/field_extraction-{lan}/'
        repo_names = f'/mnt/three-lans/{lan}-names.txt'

        run_consistency_evaluator('cdx', path_result, filepath, repo_names)
        run_consistency_evaluator('spdx', path_result, filepath, repo_names)

        logger.success('Consistency Analysis Finished.')
