$(document).ready(function(){

  var current_metric = "",
           chartName = "milestone-burndown",
              $chart = $("#"+chartName);

  if(!window.render_burndown) {
    // No start date and can't estimate start so don't try and render the burndown chart
    $chart.attr("class", "no-data milestone-info")
                .html("<i class='icon-info-sign'></i> As of yesterday " +
                      "no tickets were associated with this milestone. " + 
                      "No burn down chart will be generated until it has " +
                      "ticket data to display.");
  }
  else if(window.print_burndown) {
    // Render print friendly burn down on seperate page
    open_print_burndown();
  }
  // Render burndown on milestone page with default metric via AJAX
  else {
    get_and_draw_burndown();
    
    // Redraw the burndown on milestone page with new metric via AJAX
    $('#tickets-metric, #hours-metric, #points-metric').click(function() {
      get_and_draw_burndown($(this).attr("id").split("-")[0]);
    });
  }

  // to encourage the use of start and end dates we put the opacity at 0.6
  // and show a message to users which is hidden upon mouseover
  if (approx_start_date) {
      $.jqplot.postDrawHooks.push(start_message_warning)
      $chart.mouseover(remove_opacity);
  }

  function start_message_warning(approx_start_date) {
    $chart.css("opacity",0.6).addClass("center");
    $chart.append("<div id='no-start-date'><div> " +
                "Please set a start date for this milestone. In the meantime we " +
                "have estimated one for you.</div></div>")
  }

  function remove_opacity() {
    // remove the opacity css attribute and hide the message div
    $chart.css("opacity", 1);
    $("#no-start-date").addClass("hidden");
  }

  function burndown_options(data, print) {

    // Calculate the interval between x-axis dates (aka tickInterval)
    // 20 ticks is about right on a average sized screen
    // We plus one so that for 0.x numbers, we still get a 1 day interval
    tick_gap = Math.ceil(data['idealcurvedata'].length / 20);
    xaxis_interval = tick_gap + " day" + (tick_gap == 1 ? "": "s");

    // Options specific to milestone or print friendly pages
    if(print) {
      animateval = replotval = false;
      xaxislabel = "";
      legendlocation = "s";
      legendbackground = "#FFF";
      titletext = data['milestone_name'];
    }

    else {
      animateval = replotval = true;
      xaxislabel = 'Days in Milestone';
      legendlocation = 'n';
      legendbackground = '#DFEEFD';
      titletext = '';
    }

    // Chart options
    return {
      animate: animateval,
      animateReplot: replotval,
      grid: {
        shadow: false,
        background: '#FFF',
        borderWidth:1,
        borderColor: '#AAA',
        shadow:false
      },
      gridPadding: { top:50 },
      axes: {
        xaxis: {
          renderer:$.jqplot.DateAxisRenderer,
          tickOptions:{
            formatString: '%d %b'
          },
          label: xaxislabel,
          tickInterval: xaxis_interval,
          // IE8 can't handle yyyy-mm-dd
          min: $.datepicker.parseDate( "yy-mm-dd", data['start_date'] ).getTime(),
          max: $.datepicker.parseDate( "yy-mm-dd", data['end_date'] ).getTime()
        },
        yaxis: {
          label: data['yaxix_label'],
          min: 0
        }
      },
      highlighter: {
        show: true,
        sizeAdjust: 7.5,
        tooltipAxes: 'xy',
        tooltipLocation: "n",
        formatString: "%s &mdash; %s " + data['effort_units']
        },
      series:[
              {
                label: 'Ideal effort',
                color:'#AAA',
                showMarker: false,
                linePattern: 'dashed',
                lineWidth: 1.25,
                shadow: false
              },
              {
                label: 'Remaining effort',
                color:'#06C',
                showMarker: false,
                shadow: false
              },
              {
                label:'Team effort',
                color: '#23932C',
                showMarker: false,
                shadow: false
              }
              /*{
                label:'Work added',
                color: '#0066CC',
                showMarker: false,
                shadow: false
              }*/
             ],
      legend: {
        xoffset: 0,
        renderer: $.jqplot.EnhancedLegendRenderer,
        show: true,
        rendererOptions: {
          numberRows: 1
        },
        placement: 'outside',
        location: legendlocation
      },
      title: { text: titletext }
    };
  }

  // Ajax calls to get burndown data and render chart
  function get_and_draw_burndown(metric) {
    current_metric = metric;
    options = {
      type: 'GET',
      data: {},
      url: window.tracBaseUrl + "milestone/" + milestone_name + "/burndown",
      success: function (data) {
        remove_spinner($chart);
        if (!data['result']) {
          burndown_fail($chart);
        }
        else {
          draw_burndown(data, burndown_options(data), !metric);
        }
      },
      error: function(data, textStatus, jqXHR) {
        remove_spinner($chart);
        burndown_fail($chart);
      }
    };

    show_spinner($chart, "145px");
    if(metric) {
      $("#burndown-spinner").css("margin-top", "100px");
      options["data"]["metric"] = metric;
    }
    if (approx_start_date) {
      options["data"]["approx_start_date"] = approx_start_date;
    }
    $.ajax(options);
  }

  // Expects date as a string in yyyy-mm-dd format, with a time added for 
  // greater accuracy. We use jQuery datepicker to create the date time object
  // as IE8 can't cope with yyyy-mm-dd
  function addTime(date){
    // need to pass a timestamp as the dateaxisrenderer is timezone aware
    return $.datepicker.parseDate( "yy-mm-dd", date ).getTime();
  }

  // Function which returns a two dimensional array. Each array has a 
  // date and value, with the value reflecting some kind of work either 
  // remaining or completed on that day
  function dataSeries(curvedata){
    var series_data = [];
    for (var i=0; i < curvedata.length; i++) {
      series_data.push([addTime(curvedata[i][0]), curvedata[i][1]]);
    }
    return series_data;
  }

  function draw_burndown(data, options, is_first) {
    if(is_first) {
      draw_burndown_first(data, options);
    }
    else {
      draw_burndown_again(data, options);
    }
  }

  function draw_burndown_first(data, options) {

    // Curve data needed for jqPlot series
    burndowncurve = dataSeries(data['burndowndata']);
    teameffortcurve = dataSeries(data['teameffortdata']);
    idealcurve = dataSeries(data['idealcurvedata']);
    // we aren't calculating added curve right now #3850
    //addedcurve = dataSeries(data['workaddeddata']);

    // Render the jqPlot burn down chart
    window.plot1 = $.jqplot(chartName,
                            [idealcurve, burndowncurve, teameffortcurve],
                            options);

    // Makes the data points clickable, redirecting the user to the timeline
    var timeline_url = data['timeline_url'];
    $chart.bind('jqplotDataClick',
      function (ev, seriesIndex, pointIndex, data, neighbor, gridData) {
        // data[0] is a unix timestamp
        new_date = new Date(data[0]);
        year = new_date.getFullYear();
        // Necessary check as getDate and getMonth not always MM or DD format
        // Remember JS date months are zero based hence the +1
        if (new_date.getMonth() +1 <= 9) {
          month = "0" + (new_date.getMonth() +1);
        }
        else {
          month = new_date.getMonth() +1;
        }
        if (new_date.getDate() <= 9) {
          day = "0" + new_date.getDate();
        }
        else {
          day = new_date.getDate();
        }
        date_string = year + "-" + month + "-" + day;
        // redirect to the timeline page for that date
        window.location = (timeline_url + '&from=' + date_string);
      }
    );

    // Makes the jqPlot resize when the window is resized
    $(window).resize(function() {
      if (!data['print_burndown']) {
        plot1.animateReplot = false;
        plot1.replot();
      }
    });

  }

  function draw_burndown_again(data, options) {
    //Redraw the burn down chart with new data returned from JSON
    burndowncurve = dataSeries(data['burndowndata']);
    teameffortcurve = dataSeries(data['teameffortdata']);
    idealcurve = dataSeries(data['idealcurvedata']);
    // we aren't calculating added curve right now #3850
    //addedcurve = dataSeries(data['workaddeddata']);

    $chart.html("");
    window.plot1 = $.jqplot(chartName,
                            [idealcurve, burndowncurve, teameffortcurve],
                            options);
  }

  function open_print_burndown() {
    $chart.css({"height": "800px", "width":"1450px", "margin-bottom": "40px"});
    draw_burndown(window.data, burndown_options(window.data, true), true);

    // Style chart to be print friendly
    $(".jqplot-table-legend").css({"top": "810px", "border": 0});
    $(".jqplot-cursor-legend").css("border", 0);

    // Create an image overwriting the original canvas
    $chart.html("<img src='" + $chart.jqplotToImageStr({}) + "' />");
    window.print();
  }

  function burndown_fail($chart) {
    $chart.attr("class", "no-data milestone-info")
          .html("<i class='icon-info-sign'></i> Failed to retrieve burn down data.");
  }

  function show_spinner($chart, marginTop) {
    $chart.addClass("center")
          .append("<i id='burndown-spinner' " + (marginTop ? "style='margin-top:" + marginTop + "' " : "") +
                     "class='icon-spinner icon-spin icon-2x color-muted-dark'></i>");
  }

  function remove_spinner($chart) {
    $chart.removeClass("center");
    $("#burndown-spinner").remove();
  }

  // Open a new window with a burndown chart (print friendly)
  $('#print-burndown').click(function() {
    metric_get = current_metric ? "&metric=" + current_metric : "";
    window.open(window.tracBaseUrl + 'milestone/' + milestone_name + '/burndown?format=print' + metric_get);
  });

});