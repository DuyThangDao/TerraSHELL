const playwright = require('playwright-core');
const chromium = playwright["chromium"]
const stringify = require('csv-stringify').stringify;
const fs = require("fs")

const progressBar = require('progress');

const totalQuery = 'document.querySelector("#__next > main > div > article > div > section > div > div").childElementCount';
const reg = /\(.*\)/

async function analyzePage(page, componentLink, context) {
    await page.goto(componentLink);
    await page.waitForSelector("#__next > main > div > article")
    const total = await page.evaluate(totalQuery);

    let count = 0;
    let rres = new Set();
    for (let idx = 1; idx <= total; idx++) {
        let selector = `#__next > main > div > article > div > section > div > div > div:nth-child(${idx}) > div > div > a > div > div > span`;
        //  Try null
        if (await page.evaluate(`document.querySelector("${selector}")`) == null) {
            console.log("Cont")
            continue;
        }
        let innerText = String(await page.evaluate(`document.querySelector("${selector}").innerText`))
        if (!innerText.startsWith("aws_")) {
            continue; //  Checking edge case (only aws cloudformation ->  skip)
        }
        // console.log(innerText)
        // console.log(innerText.match(reg)[0].split(" ")[0].substring(1))
      //
        let super_total = parseInt(innerText.match(reg)[0].split(" ")[0].substring(1));
        count += super_total
        if (super_total == 0) {
          continue;
        }

        let sub_page = await context.newPage();
        let href = String(await page.evaluate(`document.querySelector("${selector}").parentElement.parentElement.parentElement.href`))
        await sub_page.goto(href)
        await sub_page.waitForSelector("#example-usage-from-github")
        
      for (let j = 0; j < super_total; j++) {
        let query2 = `document.querySelectorAll(".terraform_div > div > a:nth-child(2)")[${j}].href.split('/').slice(2, 5).join('/')`
        let ghhref = String(await sub_page.evaluate(query2));
        rres.add(ghhref);
      }
        await sub_page.close();

    }
    return [count, Array.from(rres)];
}

async function analyze() {
  const browser = await chromium.launch({headless: false});
  const context = await browser.newContext({});

  const stringifier = stringify({ header: true, columns: ["Component name", "Total reference", "Repo reference", "Repos"] });
  const filename = "./result.csv";
  const writableStream = fs.createWriteStream(filename);

  let root = await context.newPage(); // Dummy page

//   await analyzePage(root, "https://shisho.dev/dojo/providers/aws/Route_53_Resolver/")
//   await browser.close();
//   return;

  await root.goto("https://shisho.dev/dojo/providers/aws/")
  await root.waitForSelector("#__next > main > div > article")
  
  const total = await root.evaluate(totalQuery);
  console.log(`Total ${total} resource(s)`);
  const bar = new progressBar('Processing [:bar] :percent :etas', { total: total });

  for (let idx = 1; idx <= total; idx++) {
    let selector = `#__next > main > div > article > div > section > div > div > div:nth-child(${idx}) > div > div > a`
    let componentName = await root.evaluate(`document.querySelector("${selector}").text`)
    let componentLink = await root.evaluate(`document.querySelector("${selector}").href`)
    // console.log(`${componentName} : ${componentLink}`);

    let page = await context.newPage();
    let res = await analyzePage(page, componentLink, context);
    await page.close();
    // console.log(`${componentName} : ${res}`);

    stringifier.write([componentName, res[0], res[1].length, res[1].join('\n')]);
    bar.tick(1);
  }

  stringifier.pipe(writableStream);
  

  await browser.close();
}

analyze()
